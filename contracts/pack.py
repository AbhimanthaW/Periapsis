"""Mission-pack v1 structural and semantic validation."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from zipfile import BadZipFile, ZipFile
from zlib import error as CompressionError

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from marsdoc import DocumentationEngine, Package
import numpy as np
from pyproj import CRS
from pyproj.exceptions import CRSError

ROOT = Path(__file__).resolve().parent
MAX_JSON = 2_000_000
ARRAYS = {"z_m": np.dtype("<f4"), "valid_mask": np.dtype(bool), "screen_excluded_mask": np.dtype(bool)}


class PackError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(f"{code}: {detail}")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key}")
        result[key] = value
    return result


def _invalid_constant(token):
    raise ValueError(f"nonfinite JSON value {token}")


def _finite_float(token):
    result = float(token)
    if not isfinite(result):
        raise ValueError(f"nonfinite JSON value {token}")
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_constant, parse_float=_finite_float)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise PackError("INVALID_JSON", str(error)) from error


def schema(name, value):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise PackError("UNSUPPORTED_SCHEMA", f"{name} requires integer version 1")
    spec = json.loads((ROOT / f"{name}.v1.schema.json").read_bytes())
    try:
        Draft202012Validator(spec, format_checker=FormatChecker()).validate(value)
    except ValidationError as error:
        path = "/".join(map(str, error.absolute_path))
        raise PackError("INVALID_SCHEMA", f"{name} {path}: {error.message}") from error
    return value


def _read(path, limit, missing="MISSING_ARTIFACT"):
    if path.is_symlink():
        raise PackError("INVALID_ARTIFACT", f"symlink: {path.name}")
    if not path.is_file():
        raise PackError(missing, path.name)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise PackError("INVALID_ARTIFACT" if missing == "MISSING_SITE" else "CHECKSUM_MISMATCH", f"size limit: {path.name}")
    return data


def pin(path, raw):
    return {"path": path, "size_bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def center(grid, row, col):
    a, _, c0, _, e, f0 = grid["affine"]
    return c0 + a * (col + .5), f0 + e * (row + .5)


def _grid(grid, reference):
    rows, cols = grid["shape"]
    if any(type(value) is not int for value in grid["shape"]):
        raise PackError("INVALID_GRID", "shape requires integer dimensions")
    a, b, c, d, e, f = grid["affine"]
    bounds = [c, f + e * rows, c + a * cols, f]
    if (not np.isfinite([*grid["affine"], *grid["bounds_m"], *bounds, reference["native_spacing_m"]]).all()
            or a <= 0 or e >= 0 or b or d or not np.allclose(grid["bounds_m"], bounds, atol=1e-6, rtol=0)):
        raise PackError("INVALID_GRID", "expected finite north-up affine and matching bounds")
    for field in ("source_crs_wkt", "local_crs_wkt"):
        try:
            crs = CRS.from_wkt(reference[field])
        except CRSError as error:
            raise PackError("INVALID_GRID", field) from error
        axes = [(axis.direction, axis.unit_conversion_factor) for axis in crs.axis_info]
        if (not crs.is_projected or axes != [("east", 1.0), ("north", 1.0)]
                or crs.ellipsoid.semi_major_metre != 3_396_190 or crs.ellipsoid.inverse_flattening != 0
                or crs.prime_meridian.longitude != 0):
            raise PackError("INVALID_GRID", f"{field} must use the Mars 2000 sphere and metre XY")


def _terrain(raw, shape):
    arrays = {}
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if sorted(i.filename for i in infos) != sorted(f"{key}.npy" for key in ARRAYS):
                raise PackError("INVALID_TERRAIN", "unexpected or duplicate NPZ entries")
            for info in infos:
                key = info.filename.removesuffix(".npy")
                dtype = ARRAYS[key]
                size = int(np.prod(shape)) * dtype.itemsize
                if info.file_size > size + 1024:
                    raise PackError("INVALID_TERRAIN", "NPY member exceeds declared grid bounds")
                with archive.open(info) as member:
                    payload = BytesIO(member.read(size + 1025))
                if np.lib.format.read_magic(payload) != (1, 0):
                    raise PackError("INVALID_TERRAIN", "expected NPY v1 header")
                actual, fortran, actual_dtype = np.lib.format.read_array_header_1_0(payload, max_header_size=1024)
                if actual != shape or fortran:
                    raise PackError("INVALID_TERRAIN", f"shape or order of {key}")
                if actual_dtype != dtype:
                    raise PackError("INVALID_MASK" if key != "z_m" else "INVALID_TERRAIN", f"dtype of {key}")
                payload_bytes = payload.read()
                if len(payload_bytes) != size:
                    raise PackError("INVALID_TERRAIN", f"length of {key}")
                if dtype == np.dtype(bool) and any(value > 1 for value in payload_bytes):
                    raise PackError("INVALID_MASK", f"noncanonical Boolean encoding of {key}")
                arrays[key] = np.frombuffer(payload_bytes, dtype=dtype).reshape(shape)
    except PackError:
        raise
    except (BadZipFile, ValueError, EOFError, OSError, RuntimeError, CompressionError) as error:
        raise PackError("INVALID_TERRAIN", str(error)) from error
    z, valid, excluded = (arrays[key] for key in ARRAYS)
    if not np.isfinite(z[valid]).all() or not np.isnan(z[~valid]).all() or np.any(excluded & ~valid):
        raise PackError("INVALID_MASK", "validity, elevation and screening disagree")
    return arrays


def _evidence(raw, sources, reference, synthetic):
    try:
        package = Package.model_validate(decode(raw))
        engine = DocumentationEngine(package)
        source_keys = {(item["id"], item["version"]) for item in sources}
        supported = {product.id for product in package.products
                     if product.readiness == "usable" and "elevation" in product.variables
                     and (product.id, product.version) in source_keys
                     and product.source_crs and CRS.from_wkt(product.source_crs.definition).equals(CRS.from_wkt(reference["source_crs_wkt"]))
                     and product.native_spacing_m == reference["native_spacing_m"]
                     and (product.processing_level == "simulated") == synthetic}
        usable = {f.id for f in package.footprints if f.product_id in supported and f.coverage_kind == "usable_support"
                  and f.status == "canonical_verified" and f.geometry and f.geometry.type != "Global"
                  and engine.catalogue.entries[f.product_id].support_closed}
        if not usable:
            raise ValueError("no linked elevation support")
    except (ValueError, CRSError) as error:
        raise PackError("EVIDENCE_UNSUPPORTED", str(error)) from error
    return engine, usable


@dataclass(frozen=True)
class CheckedPack:
    site: dict
    evidence: DocumentationEngine
    elevations: np.ndarray
    terrain: dict | None = None
    stations: tuple = ()
    scenario: dict | None = None


def _check_scenario(stations, scenario, terrain, evidence_ids):
    allowed = terrain["valid_mask"] & ~terrain["screen_excluded_mask"]
    rows, cols = allowed.shape

    def within(cell):
        return all(type(index) is int for index in cell) and cell[0] < rows and cell[1] < cols

    endpoints = [scenario[name]["cell"] for name in ("checkpoint", "shelter")]
    approaches = [task["approach_cell"] for task in stations]
    task_ids = {task["id"] for task in stations}
    closures = scenario["closures"]
    if (len(task_ids) != len(stations) or len({c["id"] for c in closures}) != len(closures)
            or set(scenario["completed_task_ids"]) - task_ids
            or any(task["evidence_id"] not in evidence_ids for task in stations)
            or any(not within(cell) or not allowed[tuple(cell)] for cell in [*endpoints, *approaches])
            or any(not within(cell) for closure in closures for cell in closure["cells"])):
        raise PackError("INVALID_SCENARIO", "invalid, duplicate or unlinked station, endpoint or closure")


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


def check_pack(directory, *, capability, site_sha256=None):
    directory = Path(directory)
    if directory.is_symlink():
        raise PackError("INVALID_ARTIFACT", "pack directory is a symlink")
    raw_site = _read(directory / "site.json", MAX_JSON, "MISSING_SITE")
    if site_sha256 is not None and sha256(raw_site).hexdigest() != site_sha256:
        raise PackError("CHECKSUM_MISMATCH", "site.json")
    site = schema("site-pack", decode(raw_site))
    if capability not in site["capabilities"]:
        raise PackError("CAPABILITY_UNAVAILABLE", capability)
    synthetic = site["classification"] == "synthetic"
    grid = site["grid"] if synthetic else site["preview"]
    reference = site["reference"] if synthetic else grid["reference"]
    _grid(grid, reference)
    payload = {}
    names = {"site.json"}
    for role, item in site["artifacts"].items():
        name = item["path"]
        if name in names:
            raise PackError("INVALID_ARTIFACT", f"repeated path: {name}")
        names.add(name)
        limit = item["size_bytes"] if role in {"terrain", "preview_grid"} else min(MAX_JSON, item["size_bytes"])
        raw = _read(directory / name, limit, "MISSING_EVIDENCE" if role == "evidence" else "MISSING_ARTIFACT")
        if pin(name, raw) != item:
            raise PackError("CHECKSUM_MISMATCH", name)
        payload[role] = raw
    sources = schema("source-manifest", decode(payload["sources"]))["sources"]
    if len({s["id"] for s in sources}) != len(sources) or any(s["kind"] != site["classification"] for s in sources):
        raise PackError("EVIDENCE_UNSUPPORTED", "source identity or classification")
    evidence, evidence_ids = _evidence(payload["evidence"], sources, reference, synthetic)
    shape = tuple(grid["shape"])
    if synthetic:
        terrain = _terrain(payload["terrain"], shape)
        stations = schema("stations", decode(payload["stations"]))["stations"]
        scenario = schema("scenario", decode(payload["scenario"]))
        _check_scenario(stations, scenario, terrain, evidence_ids)
        return CheckedPack(_freeze(site), evidence, terrain["z_m"], _freeze(terrain), _freeze(stations), _freeze(scenario))
    raw = payload["preview_grid"]
    reference_crs = CRS.from_wkt(reference["source_crs_wkt"])
    if not reference_crs.equals(CRS.from_wkt(reference["local_crs_wkt"])):
        raise PackError("INVALID_GRID", "native preview CRS must equal its local CRS")
    window_digest = sha256(raw).hexdigest()
    try:
        source_match = any(
            s["window_sha256"] == window_digest
            and s["vertical_reference"] == reference["vertical_reference"]
            and s["native_spacing_m"] == reference["native_spacing_m"]
            and CRS.from_wkt(s["native_crs_wkt"]).equals(reference_crs)
            for s in sources
        )
    except CRSError as error:
        raise PackError("INVALID_GRID", "invalid source manifest CRS") from error
    if len(raw) != int(np.prod(shape)) * 4 or not source_match:
        raise PackError("INVALID_TERRAIN", "preview length or source lineage")
    z = np.frombuffer(raw, dtype="<f4").reshape(shape)
    if not np.isfinite(z).all():
        raise PackError("INVALID_TERRAIN", "preview must contain finite elevations")
    return CheckedPack(_freeze(site), evidence, z)
