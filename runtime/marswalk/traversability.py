"""Subsystem 03 · Traversability.

Boxes, in pipeline order:
  1. Terrain scale and support     - native vs analytical resolution, recorded not assumed
  2. Coverage and support masks    - valid cells; full 3x3 kernel support for derivatives
  3. Scale-aware roughness  (P1)   - std of residuals about a locally fitted plane
  4. Characterize surface evidence (P1) - mapped features with source + effect
  5. Slope screening               - Horn slope; optional configurable policy threshold
  6. Obstacles and exclusions      - known excluded / unknown / conditional flags
  7. Baseline routing inputs       - immutable arrays handed to routing (09)

Unknown support is always kept separate from known exclusions. Closures are
NOT applied here; they arrive per request in Subsystem 09.
"""
from dataclasses import dataclass, field

import numpy as np

from .errors import MarswalkError

# Per-cell reason codes (uint8) in BaselineRoutingInputs.reason
CELL_OK = 0
CELL_NO_DATA = 1            # unknown: source has no valid elevation
CELL_NO_KERNEL = 2          # unknown: an active derivative policy has incomplete support
CELL_PACK_SCREEN = 3        # known excluded: producer screen mask in the pack
CELL_SLOPE_POLICY = 4       # known excluded: runtime slope policy
CELL_ROUGHNESS_POLICY = 5   # known excluded: runtime roughness policy
CELL_MAPPED_OBSTACLE = 6    # known excluded: authorized mapped obstacle
REASON_NAMES = {CELL_OK: "ok", CELL_NO_DATA: "no_data", CELL_NO_KERNEL: "incomplete_kernel_support",
                CELL_PACK_SCREEN: "pack_screen", CELL_SLOPE_POLICY: "slope_policy",
                CELL_ROUGHNESS_POLICY: "roughness_policy", CELL_MAPPED_OBSTACLE: "mapped_obstacle"}
UNKNOWN_REASONS = (CELL_NO_DATA, CELL_NO_KERNEL)


# 1 ---------------------------------------------------------------- scale and support
@dataclass(frozen=True)
class TerrainSupport:
    shape: tuple
    affine: tuple              # [a, b, c0, d, e, f0], north-up
    cell_dx_m: float           # analytical spacing east-west
    cell_dy_m: float           # analytical spacing north-south
    native_spacing_m: float
    vertical_reference: str
    pack_id: str
    classification: str        # "synthetic" or source-backed
    pack_version: str | None = None

    @classmethod
    def from_affine(cls, shape, affine, *, native_spacing_m, vertical_reference="unspecified",
                    pack_id="unpacked", classification="synthetic", pack_version=None):
        a, b, _, d, e, _ = map(float, affine)
        if a <= 0 or e >= 0 or b or d:
            raise MarswalkError("INVALID_GRID", "expected a north-up affine with no skew")
        if native_spacing_m <= 0:
            raise MarswalkError("INVALID_GRID", "native spacing must be positive")
        return cls(tuple(shape), tuple(map(float, affine)), a, -e, float(native_spacing_m),
                   vertical_reference, pack_id, classification, pack_version)

    @property
    def finer_than_native(self):
        """Analytical cells smaller than the native posts add no real detail."""
        return min(self.cell_dx_m, self.cell_dy_m) < self.native_spacing_m

    def center_xy(self, row, col):
        a, _, c0, _, e, f0 = self.affine
        return c0 + a * (col + .5), f0 + e * (row + .5)


# 2 ---------------------------------------------------------------- coverage masks
def kernel_support(valid):
    """True where the cell and all 8 neighbours are valid (needed for 3x3 derivatives)."""
    padded = np.pad(valid, 1, constant_values=False)
    out = np.ones_like(valid, dtype=bool)
    rows, cols = valid.shape
    for dr in (0, 1, 2):
        for dc in (0, 1, 2):
            out &= padded[dr:dr + rows, dc:dc + cols]
    return out


# 5 ---------------------------------------------------------------- slope
def horn_slope_deg(z, valid, dx, dy):
    """Horn (1981) 3x3 slope in degrees. NaN where kernel support is incomplete."""
    east, north = horn_gradient(z, valid, dx, dy)
    return np.degrees(np.arctan(np.hypot(east, north)))


def horn_gradient(z, valid, dx, dy):
    """Dimensionless east/north components on the north-up analytical grid."""
    p = np.pad(np.where(valid, z, np.nan).astype(float), 1, constant_values=np.nan)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * dy)
    return dzdx, -dzdy


# 3 ---------------------------------------------------------------- roughness (P1)
def detrended_roughness_m(z, valid, dx, dy, window=3):
    """Std of residuals after fitting z = a*x + b*y + c in each odd window.
    NaN unless every cell in the window is valid. Does NOT estimate sub-pixel
    hazards, footing, traction or slip."""
    if window < 3 or window % 2 == 0:
        raise MarswalkError("INVALID_POLICY", "roughness window must be odd and >= 3")
    h = window // 2
    zf = np.pad(np.where(valid, z, np.nan).astype(float), h, constant_values=np.nan)
    win = np.lib.stride_tricks.sliding_window_view(zf, (window, window))
    yy, xx = np.mgrid[-h:h + 1, -h:h + 1].astype(float)
    x, y = xx * dx, -yy * dy
    sxx, syy = (x * x).sum(), (y * y).sum()
    mean = win.mean(axis=(-2, -1))
    slope_x = (win * x).sum(axis=(-2, -1)) / sxx
    slope_y = (win * y).sum(axis=(-2, -1)) / syy
    fitted = mean[..., None, None] + slope_x[..., None, None] * x + slope_y[..., None, None] * y
    return np.sqrt(((win - fitted) ** 2).mean(axis=(-2, -1)))


# 4 ---------------------------------------------------------------- surface evidence (P1)
@dataclass(frozen=True)
class SurfaceFeature:
    """A mapped landform or observation (dune, fractured rock, scarp, frost, ...).
    It EXCLUDES cells only when `authorized` is True; otherwise it is a flag."""

    id: str
    kind: str
    cells: tuple
    source_id: str
    native_scale_m: float | None = None
    uncertainty: str = "unquantified"
    authorized: bool = False


# 5/6 ------------------------------------------------------------- policy
@dataclass(frozen=True)
class ScreenPolicy:
    """Runtime exclusion policy. Thresholds are prototype ASSUMPTIONS and do not
    establish human safety. None = rely on the producer's pack screen only."""

    policy_id: str = "pack-screen-only-v1"
    slope_limit_deg: float | None = None
    roughness_limit_m: float | None = None
    roughness_window: int = 3
    provenance: str = "assumed"


# 7 ---------------------------------------------------------------- baseline inputs
@dataclass(frozen=True)
class BaselineRoutingInputs:
    support: TerrainSupport
    z_m: np.ndarray                 # float32/64, NaN where no data
    routable: np.ndarray            # bool: may be entered by the graph
    known_excluded: np.ndarray      # bool: known reason to block
    unknown: np.ndarray             # bool: insufficient evidence (kept separate)
    reason: np.ndarray              # uint8 CELL_* code per cell
    slope_deg: np.ndarray           # NaN where unsupported
    roughness_m: np.ndarray | None  # P1, None when not computed
    flagged: tuple                  # ((feature_id, kind), ...) conditional flags, not exclusions
    policy: ScreenPolicy
    notes: tuple = field(default=())

    def reason_counts(self):
        values, counts = np.unique(self.reason, return_counts=True)
        return {REASON_NAMES[int(v)]: int(c) for v, c in zip(values, counts)}


def _frozen(array):
    array = np.array(array, copy=True)
    array.setflags(write=False)
    return array


def build_baseline(support, z_m, valid_mask, screen_excluded_mask=None, *,
                   policy=ScreenPolicy(), features=()):
    """Combine coverage, pack screen, runtime policy and mapped evidence into
    immutable routing inputs. Order of precedence for the reason code:
    no data > known exclusions > incomplete kernel (only if a derivative policy is active)."""
    shape = support.shape
    z = np.asarray(z_m, dtype=float)
    valid = np.asarray(valid_mask, dtype=bool)
    screen = np.zeros(shape, bool) if screen_excluded_mask is None else np.asarray(screen_excluded_mask, bool)
    if z.shape != shape or valid.shape != shape or screen.shape != shape:
        raise MarswalkError("INVALID_TERRAIN", "array shapes must match the grid")
    if not np.isfinite(z[valid]).all():
        raise MarswalkError("INVALID_MASK", "valid cells must have finite elevations")
    if np.any(screen & ~valid):
        raise MarswalkError("INVALID_MASK", "screen may only exclude valid cells")

    dx, dy = support.cell_dx_m, support.cell_dy_m
    slope = horn_slope_deg(z, valid, dx, dy)
    rough = (detrended_roughness_m(z, valid, dx, dy, policy.roughness_window)
             if policy.roughness_limit_m is not None else None)

    reason = np.full(shape, CELL_OK, dtype=np.uint8)
    reason[~valid] = CELL_NO_DATA
    reason[valid & screen] = CELL_PACK_SCREEN
    missing_derivative = np.zeros(shape, dtype=bool)
    if policy.slope_limit_deg is not None:
        known_slope = np.isfinite(slope)
        missing_derivative |= ~known_slope
        reason[(reason == CELL_OK) & known_slope & (slope > policy.slope_limit_deg)] = CELL_SLOPE_POLICY
    if rough is not None:
        known_roughness = np.isfinite(rough)
        missing_derivative |= ~known_roughness
        reason[(reason == CELL_OK) & known_roughness & (rough > policy.roughness_limit_m)] = CELL_ROUGHNESS_POLICY
    flagged = []
    for feature in features:
        cells = tuple(tuple(c) for c in feature.cells)
        if any(not (0 <= r < shape[0] and 0 <= c < shape[1]) for r, c in cells):
            raise MarswalkError("BAD_POSITION", f"feature {feature.id} lies outside the grid")
        if feature.authorized:
            for cell in cells:
                if reason[cell] == CELL_OK:
                    reason[cell] = CELL_MAPPED_OBSTACLE
        else:
            flagged.append((feature.id, feature.kind))
    reason[(reason == CELL_OK) & missing_derivative] = CELL_NO_KERNEL

    unknown = np.isin(reason, UNKNOWN_REASONS)
    known_excluded = (reason != CELL_OK) & ~unknown
    notes = []
    if support.finer_than_native:
        notes.append("analytical grid is finer than native posts; no extra detail is implied")
    return BaselineRoutingInputs(
        support=support, z_m=_frozen(np.where(valid, z, np.nan)), routable=_frozen(reason == CELL_OK),
        known_excluded=_frozen(known_excluded), unknown=_frozen(unknown), reason=_frozen(reason),
        slope_deg=_frozen(slope), roughness_m=None if rough is None else _frozen(rough),
        flagged=tuple(flagged), policy=policy, notes=tuple(notes))


def baseline_from_pack(pack, *, policy=ScreenPolicy(), features=()):
    """Adapter for a checked synthetic pack v1 (`contracts.pack.CheckedPack`)."""
    if pack.terrain is None:
        raise MarswalkError("CAPABILITY_UNAVAILABLE", "pack has no analytical terrain (preview packs cannot route)")
    site = pack.site
    support = TerrainSupport.from_affine(
        site["grid"]["shape"], site["grid"]["affine"],
        native_spacing_m=float(site["reference"]["native_spacing_m"]),
        vertical_reference=site["reference"]["vertical_reference"],
        pack_id=site["pack_id"], classification=site["classification"], pack_version=site["pack_version"])
    return build_baseline(support, pack.terrain["z_m"], pack.terrain["valid_mask"],
                          pack.terrain["screen_excluded_mask"], policy=policy, features=features)


def local_relief_m(z, valid, dx, dy):
    """Largest absolute residual about a locally fitted plane in each 3x3
    window: a geometric proxy for obstacle height used by vehicle clearance
    checks. NaN unless the full window is valid. It cannot see objects smaller
    than the grid and says nothing about traction."""
    zf = np.pad(np.where(valid, z, np.nan).astype(float), 1, constant_values=np.nan)
    win = np.lib.stride_tricks.sliding_window_view(zf, (3, 3))
    yy, xx = np.mgrid[-1:2, -1:2].astype(float)
    x, y = xx * dx, -yy * dy
    mean = win.mean(axis=(-2, -1))
    sx = (win * x).sum(axis=(-2, -1)) / (x * x).sum()
    sy = (win * y).sum(axis=(-2, -1)) / (y * y).sum()
    fitted = mean[..., None, None] + sx[..., None, None] * x + sy[..., None, None] * y
    return np.abs(win - fitted).max(axis=(-2, -1))
