"""Fetch the two PDS TES grids using checked byte ranges."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

from workspace import build_workspace

root = build_workspace() / "science-sources"
base = "https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-5-timap-v1/mgst_9001/data/"
files = {"global_ti_night_2007.img": 51840000, "global_ti_msk_night_2007.img": 25920000}
block = 2 * 1024 * 1024

def fetch(job):
    name, size, start = job
    stop = min(start + block, size) - 1
    req = Request(base + name, headers={"Range": f"bytes={start}-{stop}"})
    with urlopen(req, timeout=100) as response:
        assert response.status == 206 and response.headers["Content-Range"] == f"bytes {start}-{stop}/{size}"
        data = response.read()
    assert len(data) == stop - start + 1
    with (root / (name + ".part")).open("r+b") as out:
        out.seek(start)
        out.write(data)

if __name__ == "__main__":
    root.mkdir(parents=True, exist_ok=True)
    for name, size in files.items():
        with (root / (name + ".part")).open("wb") as target:
            target.truncate(size)
    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(fetch, [(name, size, i) for name, size in files.items() for i in range(0, size, block)]))
    for name in files:
        (root / (name + ".part")).rename(root / (name + ".complete"))
