"""Phase 0 · Site, evidence and dimensions.

Runs before any terrain is routed. It reads the grid dimensions from the data
(never from constants), asks whether the documentation engine found eligible
local terrain evidence, and refuses grids that cannot support a Marswalk:

  1. Evidence gate     the documentation engine's capability result for the
                       requested ``local_elevation_20m`` calculation
  2. Resolution gate   analytical and native spacing <= MAX_ROUTING_CELL_M (20 m, the same
                       ceiling the repo evidence queries use)
  3. Size gate         analytical cells <= MAX_ROUTING_CELLS (1,000,000, the
                       pipeline's MAX_NATIVE_CELLS processing limit)
  4. Availability      a routable analytical terrain payload is present

It also reports an assumed horizontal feature scale of three DTM posts.
Rover rock clearance remains unverified because obstacle width and vertical
accuracy are needed to assess detection.

Loaders cover every terrain-like dataset committed on main: the Arcadia MOLA
handoff, the Jezero CTX control descriptor (and an optional local copy of the
pinned window) and the HEALPix documentation cells.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np

from .errors import (GRID_TOO_LARGE, NO_TERRAIN_EVIDENCE, TERRAIN_NOT_AVAILABLE, TERRAIN_TOO_COARSE, FAIL,
                     MarswalkError, PASS)
from .traversability import TerrainSupport

MAX_ROUTING_CELL_M = 20.0          # repo evidence queries: max_native_spacing_m 20
MAX_ROUTING_CELLS = 1_000_000      # pipeline/src/return_window_pipeline/terrain.py MAX_NATIVE_CELLS
FEATURE_SUPPORT_CELLS = 3          # smallest feature a gridded DTM resolves, in posts (assumption)
HEALPIX_RADIUS_M = 3_389_500.0     # documentation engine indexing sphere
NOT_SUPPLIED = "not_supplied"

REPO = Path(__file__).resolve().parents[2]
ARCADIA_DIR = REPO / "pipeline" / "evidence" / "arcadia-planitia"
JEZERO_DESCRIPTOR = REPO / "evidence" / "jezero" / "jezero.json"
JEZERO_WINDOW_SHA256 = "020df24a32a2ab472db7c9ddb2538073130916308edcfb6830fe22d08c3e8903"
JEZERO_WINDOW_BYTES = 4_194_304


# ------------------------------------------------------------------ dimensions
@dataclass(frozen=True)
class SiteDimensions:
    """Grid geometry read from the data. rows/cols are None for non-raster indexes."""

    cells: int
    cell_dx_m: float
    cell_dy_m: float
    native_spacing_m: float
    rows: int | None = None
    cols: int | None = None
    note: str = ""

    @property
    def cell_m(self):
        return max(self.cell_dx_m, self.cell_dy_m)

    @property
    def width_m(self):
        return None if self.cols is None else self.cols * self.cell_dx_m

    @property
    def height_m(self):
        return None if self.rows is None else self.rows * self.cell_dy_m

    @property
    def area_km2(self):
        return self.cells * self.cell_dx_m * self.cell_dy_m / 1e6

    @property
    def smallest_resolved_feature_m(self):
        return FEATURE_SUPPORT_CELLS * max(self.cell_m, self.native_spacing_m)

    def to_dict(self):
        return {"rows": self.rows, "cols": self.cols, "cells": self.cells,
                "cell_dx_m": self.cell_dx_m, "cell_dy_m": self.cell_dy_m,
                "native_spacing_m": self.native_spacing_m, "width_m": self.width_m, "height_m": self.height_m,
                "area_km2": self.area_km2, "smallest_resolved_feature_m": self.smallest_resolved_feature_m,
                "note": self.note}


def site_dimensions(support):
    """Dimensions of an analytical grid from its affine and native spacing."""
    rows, cols = support.shape
    return SiteDimensions(cells=rows * cols, cell_dx_m=float(support.cell_dx_m), cell_dy_m=float(support.cell_dy_m),
                          native_spacing_m=float(support.native_spacing_m), rows=rows, cols=cols)


# ------------------------------------------------------------------ evidence
@dataclass(frozen=True)
class EvidenceVerdict:
    """The documentation engine's answer for the requested local-terrain calculation."""

    source: str
    package_id: str
    requested_id: str
    eligible: bool
    native_spacing_m: float | None
    product_ids: tuple
    fallback_ids: tuple
    fallback_spacing_m: float | None
    reason: str | None

    def to_dict(self):
        return dict(self.__dict__, product_ids=list(self.product_ids), fallback_ids=list(self.fallback_ids))


def _spacing(calculation):
    values = [c.get("native_spacing_m") for v in calculation.get("variables", ()) for c in v.get("candidates", ())]
    values = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return min(values) if values else None


def evidence_verdict(result, *, source=""):
    """Read a marsdoc CapabilityResult (as JSON) without importing marsdoc."""
    try:
        requested = result["requested"]
        eligible = requested["eligible"]
        fallbacks = result.get("fallbacks", ())
    except (KeyError, TypeError) as error:
        raise MarswalkError("INVALID_EVIDENCE", f"not a documentation engine capability result: {error}") from error
    if not isinstance(eligible, bool):
        raise MarswalkError("INVALID_EVIDENCE", "requested.eligible must be a boolean")
    usable = [item for item in fallbacks if item.get("eligible") is True]
    reasons = [v.get("reason") for v in requested.get("variables", ()) if v.get("reason")]
    return EvidenceVerdict(
        source=source, package_id=result.get("package_id", ""), requested_id=requested.get("id", ""),
        eligible=eligible, native_spacing_m=_spacing(requested) if eligible else None,
        product_ids=tuple(requested.get("supporting_product_ids", ())),
        fallback_ids=tuple(item.get("id", "") for item in usable),
        fallback_spacing_m=min((s for s in map(_spacing, usable) if s is not None), default=None),
        reason=None if eligible else (", ".join(reasons) or requested.get("reason") or "requirements_unsatisfied"))


# ------------------------------------------------------------------ the gate
@dataclass(frozen=True)
class SiteGate:
    site_id: str
    status: str                       # "routable" | "refused"
    code: str | None
    reason: str
    dimensions: SiteDimensions
    checks: tuple                     # ((name, outcome, detail), ...)
    evidence: EvidenceVerdict | None = None
    obstacle_visibility: dict | None = None
    data: dict = field(default_factory=dict)

    @property
    def routable(self):
        return self.status == "routable"

    def require(self):
        if not self.routable:
            raise MarswalkError(self.code, self.reason)
        return self

    def to_dict(self):
        return {"site_id": self.site_id, "status": self.status, "code": self.code, "reason": self.reason,
                "dimensions": self.dimensions.to_dict(),
                "checks": [{"check": n, "outcome": o, "detail": d} for n, o, d in self.checks],
                "evidence": None if self.evidence is None else self.evidence.to_dict(),
                "obstacle_visibility": self.obstacle_visibility, "data": self.data}


def obstacle_visibility(dimensions, clearance_m):
    """Can elevation data at this scale see an obstacle as tall as the clearance?"""
    if clearance_m is None:
        return None
    feature = dimensions.smallest_resolved_feature_m
    return {"status": "not_observable",
            "clearance_m": clearance_m, "smallest_resolved_feature_m": feature,
            "detail": (f"rock clearance is unverified at {clearance_m:g} m. "
                       f"The assumed horizontal feature scale is {feature:g} m. "
                       "Obstacle widths and vertical accuracy are required to assess detection.")}


def check_site(site_id, dimensions, *, evidence=None, clearance_m=None, terrain_available=True,
               max_cell_m=MAX_ROUTING_CELL_M, max_cells=MAX_ROUTING_CELLS, data=None):
    """Evaluate every Phase 0 check, then refuse on the first failure in order:
    evidence, resolution, size, availability."""
    checks, failures = [], []
    if evidence is not None and evidence.requested_id != "local_elevation_20m":
        raise MarswalkError("INVALID_EVIDENCE", "Phase 0 requires a local_elevation_20m capability result")
    if evidence is None:
        checks.append(("evidence", NOT_SUPPLIED, "no documentation engine result supplied"))
    elif (evidence.eligible and evidence.native_spacing_m is not None
          and 0 < evidence.native_spacing_m <= max_cell_m):
        checks.append(("evidence", PASS, f"{evidence.requested_id} eligible at "
                                         f"{evidence.native_spacing_m:g} m native spacing"))
    else:
        fallback = ("" if not evidence.fallback_ids else
                    f"; only {', '.join(evidence.fallback_ids)} is supported"
                    + ("" if evidence.fallback_spacing_m is None else f" at {evidence.fallback_spacing_m:,.0f} m"))
        detail = f"{evidence.requested_id} not eligible ({evidence.reason or 'missing or excessive native spacing'}){fallback}"
        checks.append(("evidence", FAIL, detail))
        failures.append((NO_TERRAIN_EVIDENCE, detail))

    cell = dimensions.cell_m
    native = dimensions.native_spacing_m
    if max(cell, native) <= max_cell_m:
        checks.append(("resolution", PASS, f"cell {cell:g} m and native spacing {native:g} m <= {max_cell_m:g} m"))
    else:
        detail = (f"grid spacing {cell:g} m or native spacing {native:g} m exceeds "
                  f"the {max_cell_m:g} m routing ceiling")
        checks.append(("resolution", FAIL, detail))
        failures.append((TERRAIN_TOO_COARSE, detail))

    if dimensions.cells <= max_cells:
        checks.append(("size", PASS, f"{dimensions.cells:,} cells <= {max_cells:,}"))
    else:
        detail = f"{dimensions.cells:,} cells exceed the {max_cells:,} processing limit; crop the area"
        checks.append(("size", FAIL, detail))
        failures.append((GRID_TOO_LARGE, detail))

    if terrain_available is True:
        checks.append(("terrain", PASS, "analytical terrain payload present"))
    else:
        detail = terrain_available if isinstance(terrain_available, str) else "no routable terrain payload"
        checks.append(("terrain", FAIL, detail))
        failures.append((TERRAIN_NOT_AVAILABLE, detail))

    visibility = obstacle_visibility(dimensions, clearance_m)
    if failures:
        code, reason = failures[0]
        status = "refused"
    else:
        code, reason, status = None, "all Phase 0 checks passed", "routable"
    return SiteGate(site_id, status, code, reason, dimensions, tuple(checks), evidence, visibility, data or {})


def gate_for_support(support, *, site_id=None, evidence=None, clearance_m=None, **limits):
    """Phase 0 for an analytical grid that is already in memory."""
    if support.classification != "synthetic":
        limits["terrain_available"] = "contract v1 permits analytical routing only for synthetic terrain"
    return check_site(site_id or support.pack_id, site_dimensions(support), evidence=evidence,
                      clearance_m=clearance_m, **limits)


# ------------------------------------------------------------------ data on main
def _verification():
    path = ARCADIA_DIR / "verification.json"
    return json.loads(path.read_text()), path


def arcadia_context(directory=ARCADIA_DIR):
    """Arcadia Planitia MOLA handoff: exact int16 samples on the 0.25 degree grid.

    Returns (support, z_m, valid, verdict). Cell metres are measured on the
    handoff's Mars sphere at the area centre latitude."""
    directory = Path(directory)
    meta = json.loads((directory / "display-metadata.json").read_text())
    rows, cols = meta["native_shape"]
    raw = (directory / "arcadia-mola-elevation.i16le").read_bytes()
    if len(raw) != rows * cols * 2:
        raise MarswalkError("INVALID_TERRAIN", f"MOLA samples are {len(raw)} bytes, expected {rows * cols * 2}")
    z = np.frombuffer(raw, "<i2").reshape(rows, cols).astype(np.float32)
    a, _, _, _, e, _ = meta["native_crop_affine"]
    radius = float(meta["crs_wkt"].split('ELLIPSOID["Mars",')[1].split(",")[0])
    dy = math.radians(-e) * radius
    dx = math.radians(a) * radius * math.cos(math.radians(meta["center_lon_lat_deg"][1]))
    result, path = _verification()
    verdict = evidence_verdict(result["arcadia"], source=str(path.relative_to(REPO)))
    support = TerrainSupport.from_affine((rows, cols), (dx, 0, 0, 0, -dy, rows * dy), native_spacing_m=max(dx, dy),
                                         vertical_reference="MOLA areoid", pack_id=verdict.package_id,
                                         classification="source_backed", pack_version=result["arcadia"]["package_version"])
    return support, z, np.ones(z.shape, bool), verdict


def arcadia_gate(*, clearance_m=None):
    support, z, _, verdict = arcadia_context()
    data = {"source": "pipeline/evidence/arcadia-planitia (MGS MOLA MEGDR, 0.25 degree)",
            "elevation_range_m": [float(z.min()), float(z.max())]}
    return check_site("arcadia-planitia", site_dimensions(support), evidence=verdict, clearance_m=clearance_m,
                      terrain_available="MOLA context grid only; no analytical routing pack", data=data)


def jezero_dimensions():
    descriptor = json.loads(JEZERO_DESCRIPTOR.read_text())
    dx, dy = map(float, descriptor["pixelSize"])
    native = float(descriptor["source"]["nativeResolution"])
    return SiteDimensions(cells=descriptor["width"] * descriptor["height"], cell_dx_m=dx, cell_dy_m=dy,
                          native_spacing_m=native, rows=descriptor["height"], cols=descriptor["width"],
                          note="archive-verified USGS CTX window; payload kept outside the repository")


def load_jezero_window(path):
    """The pinned 1024 x 1024 Float32 window (RW_JEZERO_WINDOW), verified by size and SHA-256."""
    data = Path(path).read_bytes()
    if len(data) != JEZERO_WINDOW_BYTES or sha256(data).hexdigest() != JEZERO_WINDOW_SHA256:
        raise MarswalkError("INVALID_TERRAIN", "Jezero window size or SHA-256 differs from the pinned file")
    z = np.frombuffer(data, "<f4").reshape(1024, 1024).astype(np.float64)
    return z, np.isfinite(z)


def jezero_gate(*, clearance_m=None, window=None, crop=None):
    """Jezero CTX engineering control. Evidence is eligible at 20 m. Contract v1
    keeps it preview-only, so routing is refused with TERRAIN_NOT_AVAILABLE.
    With the pinned window, `crop` = (row0, col0, rows, cols) reports hazard
    statistics for a cropped analysis area."""
    result, path = _verification()
    verdict = evidence_verdict(result["well_studied_control"], source=str(path.relative_to(REPO)))
    dims = jezero_dimensions()
    data = {"source": "evidence/jezero/jezero.json (USGS CTX DEM, 20 m)",
            "contract": "pack v1 classifies this window as elevation_preview; routing is outside v1"}
    if window is not None:
        z, valid = load_jezero_window(window)
        r0, c0, h, w = crop or (462, 462, 100, 100)
        if not (0 <= r0 and 0 <= c0 and r0 + h <= 1024 and c0 + w <= 1024 and h >= 3 and w >= 3):
            raise MarswalkError("BAD_POSITION", "crop must lie inside the 1024 x 1024 window")
        dims = SiteDimensions(cells=h * w, cell_dx_m=dims.cell_dx_m, cell_dy_m=dims.cell_dy_m,
                              native_spacing_m=dims.native_spacing_m, rows=h, cols=w,
                              note=f"crop rows {r0}-{r0 + h - 1}, cols {c0}-{c0 + w - 1} of the verified window")
        from .traversability import horn_slope_deg, local_relief_m
        sub_z, sub_v = z[r0:r0 + h, c0:c0 + w], valid[r0:r0 + h, c0:c0 + w]
        slope = horn_slope_deg(sub_z, sub_v, dims.cell_dx_m, dims.cell_dy_m)
        relief = local_relief_m(sub_z, sub_v, dims.cell_dx_m, dims.cell_dy_m)
        finite = np.isfinite(slope)
        data["crop_analysis"] = {
            "valid_cells": int(sub_v.sum()),
            "slope_deg": {"median": float(np.nanmedian(slope)), "p95": float(np.nanpercentile(slope, 95)),
                          "max": float(np.nanmax(slope))},
            "cells_over_15deg": int((slope[finite] > 15).sum()),
            "local_relief_m": {"median": float(np.nanmedian(relief)), "max": float(np.nanmax(relief))}}
    return check_site("jezero-control", dims, evidence=verdict, clearance_m=clearance_m,
                      terrain_available="contract v1 allows routing only on synthetic packs; the Jezero window "
                                        "is elevation_preview", data=data)


def healpix_dimensions(nside=128):
    cells = 12 * nside * nside
    area_m2 = 4 * math.pi * HEALPIX_RADIUS_M ** 2 / cells
    side = math.sqrt(area_m2)
    return SiteDimensions(cells=cells, cell_dx_m=side, cell_dy_m=side, native_spacing_m=side,
                          note=f"equal-area HEALPix Nside {nside}; side is the square root of the cell area")


def healpix_gate(nside=128):
    return check_site("healpix-documentation-cells", healpix_dimensions(nside),
                      terrain_available="science and documentation index, not terrain",
                      data={"use": "choose where to go (region ranking); never route costs"})
