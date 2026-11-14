"""Checks shared by the Arcadia handoff builder and verifier."""

from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit


SEARCH_ENDPOINT = "https://stac.astrogeology.usgs.gov/api/search"
CTX_COLLECTION = "mro_ctx_controlled_usgs_dtms"
SEARCH_FILES = ("arcadia-ctx.json", "well-studied-control-ctx.json")
GRID_FILE = "arcadia-mola-elevation.i16le"
EXPECTED_FILES = {
    "README.md",
    "api-verification.json",
    "arcadia-mola-context.png",
    GRID_FILE,
    "build_arcadia_handoff.py",
    "catalog-search/searches.json",
    *(f"catalog-search/{name}" for name in SEARCH_FILES),
    "control-query.json",
    "display-metadata.json",
    "evidence-query.json",
    "evidence.json",
    "handoff_checks.py",
    "source-config.json",
    "source-manifest.json",
    "source-record.json",
    "verification.json",
    "verify_handoff.py",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verify_checksums(handoff: Path) -> dict[str, str]:
    checksums = {}
    for line in (handoff / "SHA256SUMS.txt").read_text().splitlines():
        entry = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not entry:
            raise ValueError("Malformed SHA256SUMS.txt entry")
        expected, name = entry.groups()
        if name not in EXPECTED_FILES or name in checksums:
            raise ValueError(f"Unexpected or duplicate checksum entry: {name}")
        checksums[name] = expected
    missing = EXPECTED_FILES - checksums.keys()
    if missing:
        raise ValueError(f"Missing checksum entries: {', '.join(sorted(missing))}")
    for name, expected in checksums.items():
        if digest(handoff / name) != expected:
            raise ValueError(f"SHA-256 mismatch: {name}")
    return checksums


def ring(bounds):
    west, south, east, north = bounds
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def read_catalog_searches(directory: Path) -> list[dict]:
    searches = json.loads((directory / "searches.json").read_bytes())
    if [entry["response_path"] for entry in searches] != list(SEARCH_FILES):
        raise ValueError("Expected Arcadia and Jezero CTX catalog snapshots")

    for entry in searches:
        name = entry["response_path"]
        url = urlsplit(entry["request_url"])
        params = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
        if (url._replace(query="").geturl() != SEARCH_ENDPOINT
                or entry["response_url"] != entry["request_url"]
                or set(params) != {"collections", "bbox", "limit"}
                or params["collections"] != [CTX_COLLECTION]
                or params["limit"] != ["5"]
                or len(params["bbox"]) != 1):
            raise ValueError(f"Unexpected CTX search request: {name}")
        bounds = [float(coordinate) for coordinate in params["bbox"][0].split(",")]
        west, south, east, north = bounds
        lon, lat = entry["center_lon_lat_deg"]
        if (bounds != entry["bounds_wsen_deg"]
                or not (-180 <= west < lon < east <= 180 and -90 <= south < lat < north <= 90)):
            raise ValueError(f"Catalog bounds do not match the CTX search request: {name}")
        entry["bounds_wsen_deg"] = bounds

        response_bytes = (directory / name).read_bytes()
        response = json.loads(response_bytes)
        features = response["features"]
        if (sha256(response_bytes).hexdigest() != entry["response_sha256"]
                or response["numberMatched"] != entry["number_matched"]
                or response["numberReturned"] != entry["number_returned"]
                or [feature["id"] for feature in features] != entry["sample_product_ids"]
                or len(features) != entry["number_returned"]
                or any(feature["collection"] != CTX_COLLECTION for feature in features)
                or any(link["rel"] == "next" for link in response["links"]) != entry["has_next"]):
            raise ValueError(f"Catalog response differs from the recorded comparison: {name}")

    candidate, control = searches
    if candidate["number_matched"] != 0 or candidate["has_next"] or control["number_matched"] <= 0:
        raise ValueError("Catalog comparison does not support this candidate finding")
    return searches
