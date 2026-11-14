"""Reproduce the historical EVA examples from reviewed, local source files."""
import argparse
import csv
from datetime import datetime
from hashlib import file_digest, sha256
import json
import math
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from pyproj import CRS, Transformer

from marsdoc.spatial import GEOD
from runtime.marswalk.traversability import horn_slope_deg

REPO = Path(__file__).resolve().parents[2]
RECEIPT = REPO / "documentation/examples/eva-source-receipt.json"
SITE = (77.4509, 18.4446)  # Published Octavia E. Butler landing coordinates.
SCLK = "670144481"
CTX = REPO / "evidence/jezero/jezero.json"


def digest(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return file_digest(stream, algorithm).hexdigest()


def verified(path, expected):
    if digest(path) != expected:
        raise ValueError(f"checksum mismatch: {path.name}")


def meda_row(directory, source):
    data = source["data"]
    label = directory / source["label"]["url"].rsplit("/", 1)[-1]
    verified(label, source["label"]["sha256"])
    table = directory / data["url"].rsplit("/", 1)[-1]
    verified(table, data["sha256"])
    xml = ElementTree.parse(label)
    archive_md5 = xml.findtext(".//{*}md5_checksum")
    if (table.name != xml.findtext(".//{*}file_name") or data["bytes"] != table.stat().st_size
            or archive_md5 != source["archive_md5"] or digest(table, "md5") != archive_md5):
        raise ValueError(f"PDS file identity or MD5 mismatch: {table.name}")
    if xml.findtext(".//{*}logical_identifier") != source["lid"] or xml.findtext(".//{*}version_id") != source["version"]:
        raise ValueError(f"PDS product version mismatch: {table.name}")
    with table.open(newline="") as stream:
        selected = [row for row in csv.DictReader(stream) if row["SCLK"] == SCLK]
    if len(selected) != 1:
        raise ValueError(f"expected one PDS record for {SCLK}: {table.name}")
    return selected[0]


def terrain_sample(window, point):
    # Read-only use of the archive-verified prepared input shared with marsdoc.
    evidence = json.loads((CTX.parent / "jezero-evidence.json").read_bytes())["products"][0]
    provenance = dict(item.split(": ", 1) for item in evidence["provenance"] if item.startswith("sha256"))
    verified(CTX, provenance["sha256 prepared jezero.json"])
    verified(window, provenance["sha256 little-endian float32 source window"])
    meta = json.loads(CTX.read_bytes())
    native = CRS.from_user_input(meta["projection"])
    transform = Transformer.from_crs(native.geodetic_crs, native, always_xy=True)
    x, y = transform.transform(*point, errcheck=True)
    dx, dy = meta["pixelSize"]
    left, top = meta["origin"]
    col, row = math.floor((x - left) / dx), math.floor((top - y) / dy)
    if not (1 <= row < meta["height"] - 1 and 1 <= col < meta["width"] - 1):
        raise ValueError("requested slope needs a complete 3×3 interior CTX kernel")
    raster = np.memmap(window, dtype="<f4", mode="r", shape=(meta["height"], meta["width"]))
    z = np.asarray(raster[row - 1:row + 2, col - 1:col + 2], dtype=float)
    slope = horn_slope_deg(z, np.isfinite(z), dx, dy)[1, 1]
    if not np.isfinite(slope):
        raise ValueError("CTX slope requires nine valid elevations")
    return {
        "value": float(slope),
        "status": "source_derived", "method": "horn-3x3-native-projected-grid",
        "source": meta["source"]["url"], "native_posting_m": dx, "window_row_col": [row, col],
        "window_sha256": provenance["sha256 little-endian float32 source window"],
        "elevation_kernel_m": z.tolist(),
        "scope": "One CTX DEM pixel near the MEDA example. No tactical terrain qualification.",
    }


def horizons_sample(directory, source, utc):
    artifact = directory / "horizons.txt"
    original = artifact.read_text()
    canonical = "\n".join(line for line in original.splitlines() if not line.startswith("Ephemeris / API_USER ")) + "\n"
    if sha256(canonical.encode()).hexdigest() != source["canonical_sha256"]:
        raise ValueError("Horizons response differs from the pinned scientific content")
    expected = datetime.fromisoformat(utc).strftime("%Y-%b-%d %H:%M:%S")
    if ("Target body name: Mars (499)" not in original or "Center body name: Earth (399)" not in original
            or "1-way_down_LT" not in original):
        raise ValueError("unexpected Horizons target, observer or quantity")
    table = original.split("$$SOE\n")[1].split("$$EOE")[0].strip()
    stamp, _, _, minutes, _ = next(csv.reader([table]))
    if stamp.strip() != expected + ".000":
        raise ValueError("Horizons sample does not match the pinned UTC epoch")
    return {"value": float(minutes) * 60, "status": "source_model", "method": "jpl-horizons-downleg-minutes-to-seconds",
            "source": source["url"], "time_utc": utc,
            "scope": "Mars centre to Earth centre. Propagation only, excluding relay and operations delay."}


def verify_clock(directory, clock):
    import spiceypy as spice

    paths = []
    for source in clock["kernels"]:
        path = directory / source["url"].rsplit("/", 1)[-1]
        verified(path, source["sha256"])
        paths.append(str(path))
    spice.furnsh(paths)
    try:
        et = spice.scs2e(clock["spacecraft_id"], clock["sclk"])
        utc = spice.et2utc(et, "ISOC", 3) + "Z"
    finally:
        for path in paths:
            spice.unload(path)
    if utc != clock["utc"]:
        raise ValueError("SPICE clock conversion differs from the reviewed timestamp")


def build(directory, window, output):
    receipt = json.loads(RECEIPT.read_bytes())
    rows = {key: meda_row(directory, source) for key, source in receipt["meda"].items()}
    temperature, pressure, wind, ancillary = (rows[key] for key in ("ats", "ps", "ws", "ancillary"))
    if len({r["LMST"] for r in rows.values()}) != 1 or len({r["LTST"] for r in rows.values()}) != 1:
        raise ValueError("MEDA source clocks do not agree")
    if wind["ROVER_STILL"] != "1" or float(ancillary["ROVER_VELOCITY"]) != 0:
        raise ValueError("wind example requires a stationary rover")
    north, west = (float(ancillary[key]) for key in ("ROVER_POSITION_X", "ROVER_POSITION_Y"))
    lon, lat, _ = GEOD.fwd(*SITE, math.degrees(math.atan2(-west, north)), math.hypot(north, west))
    anchor = [lon % 360, lat]
    clock = receipt["meda_clock"]
    verify_clock(directory, clock)
    rad = receipt["rad_reference"]

    def observed(key, variable, value, scope, status="historical_measurement"):
        metadata = receipt["meda"][key]
        return {
            "value": value, "method": f"meda-{variable.lower()}", "status": status,
            "source": metadata["data"]["url"], "label": metadata["label"]["url"],
            "product_id": f"{metadata['lid']}::{metadata['version']}",
            "time_utc": clock["utc"], "sclk": SCLK, "lmst": rows[key]["LMST"], "ltst": rows[key]["LTST"],
            "scope": scope,
        }
    p, t, w, zenith = (float(row[key]) for row, key in (
        (pressure, "PRESSURE"), (temperature, "ATS_LOCAL_TEMP1"),
        (wind, "HORIZONTAL_WIND_SPEED"), (ancillary, "SOLAR_ZENITHAL_ANGLE"),
    ))
    if not (0 < p < 2000 and 100 < t < 400 and 0 <= w < 100 and 0 <= zenith <= 180):
        raise ValueError("MEDA normalized values outside expected range or contain fill")
    result = {
        "jezero-sol36": {
            "anchor_lon_lat": anchor,
            "scope": "Perseverance sol 36, one matched spacecraft-clock record. Anchor uses published landing coordinates and reported rover offsets. Cell membership only.",
            "fields": {
                "temperature": observed("ats", "ATS_LOCAL_TEMP1", t, "Single mast thermocouple; sensor orientation 50 degrees."),
                "wind_speed": observed("ws", "HORIZONTAL_WIND_SPEED", w, "Derived horizontal wind, rover stationary. Row uncertainty and boom flags blank."),
                "atmospheric_pressure": observed("ps", "PRESSURE", p, "Derived pressure, transducer 1. Row uncertainty blank."),
                "solar_illumination": observed("ancillary", "SOLAR_ZENITHAL_ANGLE", round(90 - zenith, 2),
                                               "Solar elevation in rover local-level frame. No irradiance or shadow inference.", "source_model"),
                "communication_latency": horizons_sample(directory, receipt["horizons"], clock["utc_rounded_to_second"]),
                "terrain_slope": terrain_sample(window, anchor),
            },
        },
        "gale-rad": {
            "anchor_lon_lat": [137.4417, -4.5895],
            "scope": "Curiosity early surface traverse at Gale. Bradbury Landing indexes this regional time-series statistic; the cell is a discovery anchor.",
            "fields": {"radiation_dose_rate": {
                "value": 0.210, "status": "historical_summary", "method": "hassler-et-al-table-1-gcr-tissue-like",
                "source": rad["publication"], "source_table": rad["table"],
                "reported_plus_minus_mgy_day": 0.040,
                "observed_from": "2012-08-07", "observed_through": "2013-06-01",
                "scope": "Published first ~300 sols, RAD E-detector tissue-like GCR absorbed dose rate. No astronaut or future dose.",
            }},
        },
    }
    output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path)
    parser.add_argument("jezero_window", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.sources, args.jezero_window, args.output)
