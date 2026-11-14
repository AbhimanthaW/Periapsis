"""Capture a bounded, reproducible inventory from the Mars STAC endpoint."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen
import time

from workspace import build_workspace

ROOT = build_workspace()
BASE = "https://stac.astrogeology.usgs.gov/api/search"
JOBS = {
    "themis": ("mo_themis_controlled_mosaics", None, 4),
    "hirise-dtm": ("mro_hirise_socet_dtms", None, 18),
    "arcadia-ctx": ("mro_ctx_controlled_usgs_dtms", "-171.90145369,48.9862569,-171.79854631,49.0537431", 3),
    "jezero-ctx": ("mro_ctx_controlled_usgs_dtms", "77.41442646,18.4262569,77.48557354,18.4937431", 3),
    "arcadia-hirise": ("mro_hirise_uncontrolled_observations", "-171.90145369,48.9862569,-171.79854631,49.0537431", 3),
    "jezero-hirise": ("mro_hirise_uncontrolled_observations", "77.41442646,18.4262569,77.48557354,18.4937431", 4),
}

def snapshot(job):
    name, (collection, bbox, page_limit) = job
    directory = ROOT / "catalogues" / name
    directory.mkdir(parents=True, exist_ok=True)
    params = {"collections": collection, "limit": 100}
    if bbox:
        params["bbox"] = bbox
    url = BASE + "?" + urlencode(params)
    initial = url
    matched = None
    ids = set()
    rows = 0
    for page in range(page_limit):
        if not url:
            break
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in {
            "stac.astrogeology.usgs.gov", "g6goyz4w56.execute-api.us-west-2.amazonaws.com"
        }:
            raise ValueError(f"Unexpected catalogue URL {url}")
        target = directory / f"{page:03}.json"
        if target.exists():
            raw = target.read_bytes()
        else:
            for attempt in range(3):
                try:
                    with urlopen(url, timeout=15) as response:
                        raw = response.read(25 * 1024 * 1024 + 1)
                    if len(raw) > 25 * 1024 * 1024:
                        raise ValueError("Catalogue page exceeds size cap")
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
        document = json.loads(raw)
        features = document["features"]
        if not isinstance(features, list) or any(f["collection"] != collection for f in features):
            raise ValueError(f"Unexpected catalogue items in {name}")
        if page == 0:
            matched = document.get("numberMatched")
        ids.update(f["id"] for f in features)
        rows += len(features)
        target.write_bytes(raw)
        url = next((link["href"] for link in document.get("links", []) if link["rel"] == "next"), None)
    report = dict(request_url=initial, collection=collection, bbox=bbox,
                  reported_matches=matched, rows=rows, unique_ids=len(ids),
                  pagination_exhausted=url is None, count_reconciled=matched == len(ids) == rows)
    (directory / "snapshot.json").write_text(json.dumps(report, indent=2) + "\n")
    return name, report

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {name: pool.submit(snapshot, (name, spec)) for name, spec in JOBS.items()}
        for name, future in futures.items():
            try:
                print(*future.result(), flush=True)
            except (OSError, ValueError, KeyError) as error:
                print(f"{name}: {error}", flush=True)
