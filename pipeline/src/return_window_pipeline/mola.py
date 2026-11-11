"""Interpret the pinned PDS4 MEG004 1.1 topography and count products."""

import math

import numpy as np
from rasterio.enums import MaskFlags

from .coordinates import validate_crs
from .errors import IntegrityError

LID_PREFIX = "urn:nasa:pds:mgs_mola_topography_derived:data_meg004:"
TOPOGRAPHY = LID_PREFIX + "megt90n000cb"
COUNTS = LID_PREFIX + "megc90n000cb"
FRAME = "IAU2000_MARS"
VERTICAL = "MOLA topography: planetary radius minus the GMM3 mgm1025 degree/order 50 areoid, per product label"
RADIUS = 3396000.0
POST = math.radians(0.25) * RADIUS
AFFINE = (POST, 0, -720 * POST, 0, -POST, 360 * POST)
NATIVE_CRS = "+proj=eqc +R=3396000 +lat_ts=0 +lon_0=180 +units=m +type=crs"


def validate_product(label: dict, reference, *, counts: bool = False) -> None:
    """Check the documented adapter, independently of GDAL's interpretation."""
    lid = COUNTS if counts else TOPOGRAPHY
    stem = lid.rsplit(":", 1)[-1]
    if label["logical_identifier"] != lid or label["label_version"] != "1.1":
        raise IntegrityError("Unsupported PDS4 product; only the pinned MEG004 1.1 pair is qualified")
    if reference.frame not in {FRAME, FRAME + ", as declared in the PDS4 product label"}:
        raise IntegrityError("Configured frame conflicts with the MEG004 frame")
    if (reference.latitude_type, reference.longitude_direction, reference.longitude_domain,
        reference.semi_major_m, reference.semi_minor_m) != ("planetocentric", "east", "0_360", RADIUS, RADIUS):
        raise IntegrityError("Configured spatial conventions conflict with the MEG004 adapter")
    if reference.vertical_reference != VERTICAL or reference.vertical_unit != "m":
        raise IntegrityError("Configured vertical reference conflicts with the MEG004 topography datum")
    expected = {
        "target": "Mars", "frame": FRAME, "frame_origin": "Mars", "central_body": "Mars",
        "frame_latitude_type": "Planetocentric", "latitude_type": "planetocentric",
        "longitude_direction": "Positive East", "radii_m": [RADIUS] * 3,
        "planetary_bounds": {"west": 0, "east": 360, "south": -90, "north": 90},
        "bounds_units": ["deg"] * 4, "map_projection": "Equirectangular",
        "data_file": stem + ".img", "shape": [720, 1440], "data_type": "SignedMSB2",
        "axes": 2, "axis_order": "Last Index Fastest", "axis_sequence": {"Line": 1, "Sample": 2},
        "offset_bytes": 0, "offset_unit": "byte", "scale": 1, "value_offset": 0,
        "special_constants": [], "value_unit": None if counts else "meter",
    }
    for key, value in expected.items():
        if label[key] != value:
            raise IntegrityError(f"MEG004 label {key} conflicts with the supported adapter")
    expected_grid = {
        "standard_parallel_1": (0, "deg"), "longitude_of_central_meridian": (180, "deg"),
        "pixel_resolution_x": (POST / 1000, "km/pixel"), "pixel_resolution_y": (POST / 1000, "km/pixel"),
        "pixel_scale_x": (4, "pixel/deg"), "pixel_scale_y": (4, "pixel/deg"),
        "upperleft_corner_x": (AFFINE[2], "m"), "upperleft_corner_y": (AFFINE[5], "m"),
    }
    for key, (value, unit) in expected_grid.items():
        entry = label["grid"][key]
        # The label origin is rounded to millimetres.
        if entry is None or entry[1] != unit or not math.isclose(entry[0], value, rel_tol=0, abs_tol=0.001 if unit == "m" else 1e-9):
            raise IntegrityError(f"MEG004 label {key} conflicts with the analytical grid")
    description = " ".join((label["description"] or "").lower().split())
    comment = " ".join((label["file_comment"] or "").lower().split())
    if counts:
        if "number of observations" not in description or "number of observations per pixel" not in comment:
            raise IntegrityError("MEG004 companion label does not describe observation counts")
    elif "planetary radius minus the areoid radius" not in description or "gmm3 (mgm1025) evaluated to degree and order 50" not in comment:
        raise IntegrityError("MEG004 label does not support the configured vertical reference")


def validate_grid(dataset, crs, reference) -> None:
    """Check the selected reader against the label and independent grid control."""
    expected = validate_crs(NATIVE_CRS, reference, require_metric=True)
    def parameters(operation):
        # GDAL may omit the default zero latitude of natural origin.
        values = {"8801": (0.0, math.pi / 180)}
        values.update({p.code: (p.value, p.unit_conversion_factor) for p in operation.params})
        return values

    # GDAL represents the PDS datum with its own name. The frame itself was
    # verified in the PDS label. Compare the conversion, not the datum name.
    operation = crs.coordinate_operation
    if (dataset.driver != "PDS4" or dataset.count != 1 or dataset.shape != (720, 1440)
            or not crs.is_projected or operation is None
            or operation.method_code != expected.coordinate_operation.method_code
            or parameters(operation) != parameters(expected.coordinate_operation)
            or [axis.direction for axis in crs.axis_info] != ["east", "north"]
            or any(axis.unit_conversion_factor != 1.0 for axis in crs.axis_info)
            or not np.allclose(tuple(dataset.transform)[:6], AFFINE, rtol=0, atol=0.001)
            or dataset.dtypes != ("int16",) or dataset.scales != (1.0,)
            or dataset.offsets != (0.0,) or dataset.nodata is not None
            or dataset.mask_flag_enums != ([MaskFlags.all_valid],)):
        raise IntegrityError("Decoded MEG004 grid or encoding conflicts with the authoritative product")
