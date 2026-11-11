from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from affine import Affine
import numpy as np
import rasterio

from return_window_pipeline.errors import ConfigurationError, CoordinateError, IntegrityError
from return_window_pipeline.ingestion import discard_staging, ingest, verify_workspace
from return_window_pipeline.models import SourceSpec
from return_window_pipeline.raster import inspect_observation_support

CRS = "+proj=eqc +R=3396000 +lat_ts=0 +lon_0=180 +units=m +type=crs"


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="return-window-tests-")
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "terrain.tif"
        self.workspace = self.base / "workspace"
        self.write_raster()
        self.configuration = {
            "schema_version": 1, "asset_id": "test-terrain", "source_version": "1",
            "role": "elevation", "provider": "Automated test fixture", "attribution": "Synthetic test data",
            "access_rights": "Local fixture", "entrypoint": self.source.name,
            "reference": {"body": "Mars", "semi_major_m": 3396000, "semi_minor_m": 3396000,
                          "latitude_type": "planetocentric", "longitude_direction": "east", "longitude_domain": "0_360",
                          "frame": "Test sphere", "vertical_unit": "m", "vertical_reference": "Synthetic test datum"},
            "members": [{"name": self.source.name, "uri": str(self.source)}],
        }

    def tearDown(self):
        self.assertEqual(self.base.parent, Path(tempfile.gettempdir()).resolve())
        self.temporary.cleanup()

    def write_raster(self, *, crs=CRS, unit="metre", values=None, internal_mask=None):
        values = np.array([[0, 10], [-9999, 30]], dtype="float32") if values is None else values
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(self.source, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32", crs=crs, transform=Affine(5, 0, 100, 0, -5, 200), nodata=-9999) as dataset:
                dataset.write(values, 1)
                if unit:
                    dataset.set_band_unit(1, unit)
                if internal_mask is not None:
                    dataset.write_mask(internal_mask)

    def spec(self):
        return SourceSpec.from_dict(deepcopy(self.configuration), self.base)

    def test_ingests_real_raster_structure_and_preserves_source(self):
        original = self.source.read_bytes()
        record, path, reused = ingest(self.spec(), self.workspace)
        self.assertFalse(reused)
        self.assertEqual(record["raster"]["shape"], [2, 2])
        self.assertEqual(record["raster"]["valid_pixels"], 3)
        self.assertEqual(record["raster"]["raw_value_range"], [0, 30])
        self.assertEqual(record["raster"]["pixel_center_0_0"], [102.5, 197.5])
        cached = self.workspace / "cache" / "bundles" / record["bundle_sha256"] / self.source.name
        self.assertEqual(cached.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertTrue(path.is_file())
        self.assertEqual(set(record["gate_results"].values()), {"Not evaluated"})

    def test_verified_cache_is_reused_without_original(self):
        first, path, _ = ingest(self.spec(), self.workspace)
        self.source.unlink()
        second, second_path, reused = ingest(self.spec(), self.workspace, offline=True)
        self.assertTrue(reused)
        self.assertEqual(second, first)
        self.assertEqual(path, second_path)

    def test_cache_tampering_is_detected(self):
        record, _, _ = ingest(self.spec(), self.workspace)
        cached = self.workspace / "cache" / "bundles" / record["bundle_sha256"] / self.source.name
        data = cached.read_bytes()
        cached.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaises(IntegrityError):
            verify_workspace(self.workspace)

    def test_expected_checksum_mismatch_is_quarantined(self):
        self.configuration["members"][0]["expected_sha256"] = "0" * 64
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace)
        self.assertEqual(len(list((self.workspace / "quarantine").glob("*/failure.json"))), 1)
        self.assertFalse((self.workspace / "registry").exists())

    def test_expected_checksum_is_verified(self):
        self.configuration["members"][0]["expected_sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        record, _, _ = ingest(self.spec(), self.workspace)
        self.assertTrue(record["members"][0]["checksum_pin_verified"])

    def test_corrupt_raster_is_quarantined(self):
        self.source.write_bytes(b"This is not a raster")
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace)
        self.assertTrue(list((self.workspace / "quarantine").glob("*/terrain.tif")))

    def test_earth_raster_is_rejected(self):
        self.write_raster(crs="EPSG:4326")
        with self.assertRaises(CoordinateError):
            ingest(self.spec(), self.workspace)

    def test_missing_crs_is_rejected(self):
        self.write_raster(crs=None)
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace)

    def test_nonfinite_pixels_are_not_valid(self):
        self.write_raster(values=np.array([[np.nan, 10], [np.inf, 30]], dtype="float32"))
        record, _, _ = ingest(self.spec(), self.workspace)
        self.assertEqual(record["raster"]["valid_pixels"], 2)

    def test_explicit_mask_preserves_valid_zero(self):
        self.write_raster(internal_mask=np.array([[255, 0], [0, 255]], dtype="uint8"))
        record, _, _ = ingest(self.spec(), self.workspace)
        self.assertEqual(record["raster"]["valid_pixels"], 2)
        self.assertEqual(record["raster"]["raw_value_range"], [0, 30])

    def test_external_mask_must_be_preserved(self):
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
            with rasterio.open(self.source, "r+") as dataset:
                dataset.write_mask(np.array([[255, 0], [0, 255]], dtype="uint8"))
        with self.assertRaises(ConfigurationError):
            ingest(self.spec(), self.workspace)
        mask = Path(str(self.source) + ".msk")
        self.configuration["members"].append({"name": mask.name, "uri": str(mask)})
        record, _, _ = ingest(self.spec(), self.workspace)
        self.assertEqual(record["raster"]["valid_pixels"], 2)
        self.assertEqual(len(record["members"]), 2)

    def test_vertical_units_are_not_inferred_from_horizontal_units(self):
        self.write_raster(unit="km")
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace)

    def test_scale_and_offset_are_preserved_separately(self):
        with rasterio.open(self.source, "r+") as dataset:
            dataset.scales = (0.1,)
            dataset.offsets = (100,)
        record, _, _ = ingest(self.spec(), self.workspace)
        self.assertEqual(record["raster"]["raw_value_range"], [0, 30])
        self.assertEqual(record["raster"]["scaled_value_range"], [100, 103])
        self.assertEqual(record["raster"]["scale"], 0.1)
        self.assertEqual(record["raster"]["offset"], 100)

    def test_observation_support_is_separate_from_validity(self):
        record, _, _ = ingest(self.spec(), self.workspace)
        counts = self.base / "counts.tif"
        with rasterio.open(counts, "w", driver="GTiff", height=2, width=2, count=1, dtype="int16", crs=CRS, transform=Affine(5, 0, 100, 0, -5, 200), nodata=-9999) as dataset:
            dataset.write(np.array([[0, 2], [-9999, 1]], dtype="int16"), 1)
        result = inspect_observation_support(counts, record["raster"], self.spec().reference)
        self.assertEqual(result["valid_count_cells"], 3)
        self.assertEqual(result["cells_with_observations"], 2)
        self.assertEqual(result["zero_or_missing_count_cells"], 2)
        self.assertEqual(record["raster"]["valid_pixels"], 3)

    def test_misaligned_observation_support_is_rejected(self):
        record, _, _ = ingest(self.spec(), self.workspace)
        counts = self.base / "counts.tif"
        with rasterio.open(counts, "w", driver="GTiff", height=2, width=2, count=1, dtype="int16", crs=CRS, transform=Affine(5, 0, 105, 0, -5, 200)) as dataset:
            dataset.write(np.ones((2, 2), dtype="int16"), 1)
        with self.assertRaises(IntegrityError):
            inspect_observation_support(counts, record["raster"], self.spec().reference)

    def test_non_count_values_cannot_be_observation_support(self):
        record, _, _ = ingest(self.spec(), self.workspace)
        counts = self.base / "counts.tif"
        for invalid_value in [-1.0, 0.5]:
            with self.subTest(value=invalid_value):
                with rasterio.open(counts, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32", crs=CRS, transform=Affine(5, 0, 100, 0, -5, 200)) as dataset:
                    dataset.write(np.full((2, 2), invalid_value, dtype="float32"), 1)
                with self.assertRaises(IntegrityError):
                    inspect_observation_support(counts, record["raster"], self.spec().reference)

    def test_size_limit_is_enforced(self):
        self.configuration["max_member_bytes"] = 10
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace)

    def test_offline_cache_miss_does_not_fetch(self):
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace, offline=True)
        self.assertFalse((self.workspace / "cache").exists())

    def test_refresh_does_not_overwrite_changed_pinned_source(self):
        record, path, _ = ingest(self.spec(), self.workspace)
        before = path.read_bytes()
        self.write_raster(values=np.full((2, 2), 80, dtype="float32"))
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.workspace, refresh=True)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(verify_workspace(self.workspace)), 1)

    def test_unsafe_and_duplicate_names_are_rejected(self):
        for name in ["../terrain.tif", "CON", "terrain.tif."]:
            self.configuration["members"][0]["name"] = name
            with self.assertRaises(ConfigurationError):
                self.spec()
        self.configuration["members"][0]["name"] = "terrain.tif"
        self.configuration["members"].append(dict(self.configuration["members"][0]))
        with self.assertRaises(ConfigurationError):
            self.spec()

    def test_unknown_configuration_and_missing_conventions_fail(self):
        self.configuration["invented"] = True
        with self.assertRaises(ConfigurationError):
            self.spec()
        del self.configuration["invented"]
        del self.configuration["reference"]["latitude_type"]
        with self.assertRaises(ConfigurationError):
            self.spec()

    def test_staging_cleanup_refuses_arbitrary_directory(self):
        with self.assertRaises(IntegrityError):
            discard_staging(self.base, self.workspace)
        self.assertTrue(self.source.exists())
