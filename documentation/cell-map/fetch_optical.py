"""Snapshot the ODE CTX footprint archive with checked range requests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

from workspace import build_workspace

root = build_workspace() / "expansion-sources"
name = "mars_mro_ctx_edr_c0a.zip"
url = "https://ode.rsl.wustl.edu/mars/datafile/derived_products/coverageshapefiles/mars/mro/ctx/edr/" + name
size = 38448739
block = 2 * 1024 * 1024

def fetch(start):
    stop = min(start + block, size) - 1
    req = Request(url, headers={"Range": f"bytes={start}-{stop}", "If-Match": '"aa49f797039dd1:0"'})
    with urlopen(req, timeout=100) as response:
        if response.status != 206 or response.headers["Content-Range"] != f"bytes {start}-{stop}/{size}":
            raise ValueError("Unexpected CTX source range")
        data = response.read()
    if len(data) != stop - start + 1:
        raise ValueError("Truncated CTX source range")
    return data

if __name__ == "__main__":
    root.mkdir(parents=True, exist_ok=True)
    with (root / (name + ".part")).open("wb") as target, ThreadPoolExecutor(max_workers=10) as pool:
        for data in pool.map(fetch, range(0, size, block)):
            target.write(data)
    with ZipFile(root / (name + ".part")) as archive:
        if archive.testzip() is not None:
            raise ValueError("Invalid CTX archive")
    (root / (name + ".part")).rename(root / name)
