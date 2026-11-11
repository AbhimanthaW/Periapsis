"""Independent MEG004 byte, mask and geographic-control check. Run without -O."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import rasterio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("configs/mola-global-4ppd-topography.json"))
    args = parser.parse_args()
    spec = json.loads(args.config.read_text())
    records = list((args.workspace / "registry").glob(f"{spec['asset_id']}--{spec['source_version']}--*.json"))
    assert len(records) == 1
    raw_record = records[0].read_bytes()
    record = json.loads(raw_record)
    bundle = args.workspace / "cache" / "bundles" / record["bundle_sha256"]
    for member in spec["members"]:
        assert sha256((bundle / member["name"]).read_bytes()).hexdigest() == member["expected_sha256"], member["name"]

    samples = {}
    for label in (spec["entrypoint"], spec["support_entrypoint"]):
        image = (bundle / label).with_suffix(".img")
        values = np.frombuffer(image.read_bytes(), dtype=">i2").reshape(720, 1440)
        with rasterio.open(bundle / label) as dataset:
            assert dataset.shape == values.shape
            assert np.array_equal(dataset.read(1), values)
            assert np.all(dataset.read_masks(1) == 255)
            assert dataset.nodata is None
            assert dataset.scales == (1.0,) and dataset.offsets == (0.0,)
            controls = []
            for row, col in ((0, 0), (359, 719), (360, 720), (719, 1439)):
                x, y = dataset.xy(row, col)
                lon, lat = 180 + math.degrees(x / 3396000), math.degrees(y / 3396000)
                assert abs(lon - (col + 0.5) / 4) < 1e-7
                assert abs(lat - (90 - (row + 0.5) / 4)) < 1e-7
                controls.append([row, col, round(lon, 6), round(lat, 6), int(values[row, col])])
        samples[label] = {
            "shape": list(values.shape), "range": [int(values.min()), int(values.max())],
            "zero_cells": int(np.count_nonzero(values == 0)),
            "positive_cells": int(np.count_nonzero(values > 0)),
            "controls_row_col_lon_lat_value": controls,
        }

    topo, counts = samples[spec["entrypoint"]], samples[spec["support_entrypoint"]]
    assert topo["range"] == [-8068, 21134] and topo["zero_cells"] == 147
    assert counts["range"] == [0, 2611] and counts["zero_cells"] == 9137 and counts["positive_cells"] == 1_027_663
    assert record["raster"]["valid_pixels"] == 1_036_800
    assert record["observation_support"]["zero_count_cells"] == counts["zero_cells"]
    assert record["observation_support"]["missing_count_cells"] == 0
    assert record["observation_support"]["cells_with_observations"] == counts["positive_cells"]
    print(json.dumps({"member_pins_verified": len(spec["members"]), "record_file_sha256": sha256(raw_record).hexdigest(),
                      "samples": samples}, indent=2))


if __name__ == "__main__":
    main()
