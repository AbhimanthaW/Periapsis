from contextlib import redirect_stdout, redirect_stderr
from hashlib import file_digest, sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import rasterio

from return_window_pipeline.cli import main
from return_window_pipeline.ingestion import ingest
from return_window_pipeline.models import SourceSpec


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "mola-global-4ppd-topography.json"
REGIONS = ROOT.parent / "web" / "src" / "atlas" / "regions.json"
WORKSPACE = Path(os.environ.get("RW_MOLA_WORKSPACE", ROOT / "data"))


class GlobalAtlasTests(unittest.TestCase):
    def run_atlas(self, command, directory, expected_exit=0):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            destination = "--output" if command == "build-global-atlas" else "--directory"
            status = main([command, str(CONFIG), "--workspace", str(WORKSPACE),
                           "--regions", str(REGIONS), destination, str(directory)])
        self.assertEqual(status, expected_exit, errors.getvalue())
        return json.loads(output.getvalue() if status == 0 else errors.getvalue())

    def test_build_validate_and_reject_rehashed_global_raster(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp) / "atlas"
            report = self.run_atlas("build-global-atlas", directory)
            self.assertEqual(report, self.run_atlas("validate-global-atlas", directory))
            self.assertEqual(report["bounds_deg"], [-180, -90, 180, 90])
            self.assertEqual(report["coverage"], {
                "total_cells": 1_036_800, "valid_elevation_cells": 1_036_800,
                "cells_with_observations": 1_027_663, "zero_observation_cells": 9137, "missing_count_cells": 0,
            })
            record, _, _ = ingest(SourceSpec.load(CONFIG), WORKSPACE, offline=True)
            bundle = WORKSPACE / "cache" / "bundles" / record["bundle_sha256"]
            for layer, member in (("elevation", "megt90n000cb.img"), ("observation-counts", "megc90n000cb.img")):
                raw = np.frombuffer((bundle / member).read_bytes(), dtype=">i2").reshape(720, 1440)
                with rasterio.open(directory / f"{layer}.tif") as dataset:
                    self.assertEqual(dataset.xy(0, 0), (-179.875, 89.875))
                    self.assertEqual(dataset.xy(719, 1439), (179.875, -89.875))
                    output = dataset.read(1)
                    np.testing.assert_array_equal(output[:, :720], raw[:, 720:])
                    np.testing.assert_array_equal(output[:, 720:], raw[:, :720])

            index_path = directory / "region-index.json"
            original_index = index_path.read_bytes()
            index = json.loads(original_index)
            catalog_bytes = REGIONS.read_bytes()
            expected_regions = json.loads(catalog_bytes)["regions"]
            self.assertEqual(report["region_index"]["catalog_sha256"], sha256(catalog_bytes).hexdigest())
            self.assertEqual(report["region_index"]["region_count"], len(expected_regions))
            self.assertEqual(len(index["regions"]), len(expected_regions))
            with rasterio.open(directory / "elevation.tif") as elevation_grid, \
                    rasterio.open(directory / "observation-counts.tif") as counts_grid:
                elevation_values, count_values = elevation_grid.read(1), counts_grid.read(1)
                for sample, region in zip(index["regions"], expected_regions, strict=True):
                    lon, lat = region["geography"]["center"]
                    row, col = elevation_grid.index(-180 if lon == 180 else lon, lat)
                    row = min(row, elevation_grid.height - 1)
                    self.assertEqual(sample, {
                        "region_id": region["id"],
                        "name": region["name"],
                        "geography_status": region["geography"]["status"],
                        "center_lon_lat_deg": [lon, lat],
                        "cell_row_col": [row, col],
                        "elevation_m": int(elevation_values[row, col]),
                        "observation_count": int(count_values[row, col]),
                    })

            manifest_path = directory / "atlas-manifest.json"
            original_manifest = manifest_path.read_bytes()
            manifest = json.loads(original_manifest)
            index["regions"][0]["elevation_m"] += 1
            altered_index = json.dumps(index).encode()
            index_path.write_bytes(altered_index)
            manifest["region_index"].update(bytes=len(altered_index), sha256=sha256(altered_index).hexdigest())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_atlas("validate-global-atlas", directory, expected_exit=2)
            self.assertIn("entries differ", result["message"])
            index_path.write_bytes(original_index)
            manifest = json.loads(original_manifest)

            elevation = directory / "elevation.tif"
            with rasterio.open(elevation, "r+") as dataset:
                values = dataset.read(1)
                values[0, 0] += 1
                dataset.write(values, 1)
            with elevation.open("rb") as stream:
                manifest["layers"]["elevation"].update(
                    bytes=elevation.stat().st_size, sha256=file_digest(stream, "sha256").hexdigest(),
                )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_atlas("validate-global-atlas", directory, expected_exit=2)
            self.assertIn("differ from the pinned source", result["message"])

            elevation.unlink()
            result = self.run_atlas("validate-global-atlas", directory, expected_exit=2)
            self.assertIn("inventory", result["message"])
