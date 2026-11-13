from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from affine import Affine
import numpy as np
from rasterio import open as open_raster
from rasterio.io import MemoryFile

from return_window_pipeline.coordinates import validate_crs
from return_window_pipeline.errors import ConfigurationError, CoordinateError, IntegrityError
from return_window_pipeline.ingestion import ingest
from return_window_pipeline.models import MarsReference
from return_window_pipeline.regional import ELEVATION_PREVIEW, MANIFEST, build_preview, load_job, verify_preview
from return_window_pipeline.terrain import prepare_terrain


CRS = "+proj=eqc +R=3396000 +units=m +type=crs"
REFERENCE = {
    "body": "Mars", "semi_major_m": 3396000, "semi_minor_m": 3396000,
    "latitude_type": "planetocentric", "longitude_direction": "east",
    "longitude_domain": "-180_180", "frame": "Controlled Mars fixture",
    "vertical_unit": "m", "vertical_reference": "Controlled reference",
}

TEST_REFERENCE = MarsReference.parse(REFERENCE)


def populate(dataset, values, scale=1, offset=0):
    dataset.write(np.asarray(values, dtype=np.float32), 1)
    dataset.scales = (scale,)
    dataset.offsets = (offset,)


class TerrainTests(unittest.TestCase):
    def process(self, values, bounds, factor=1, reference=TEST_REFERENCE, scale=1, offset=0):
        height, width = values.shape
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff", dtype="float32", count=1, height=height, width=width,
                crs=CRS, transform=Affine(20, 0, 0, 0, -20, height * 20), nodata=-9999,
            ) as dataset:
                populate(dataset, values, scale=scale, offset=offset)
                return prepare_terrain(dataset, band=1, reference=reference, bounds_m=bounds, factor=factor)

    def test_flat_zero_is_valid_and_halo_supports_all_crop_cells(self):
        terrain = self.process(np.zeros((6, 6)), (20, 20, 100, 100))
        self.assertTrue(terrain.elevation_valid.all())
        self.assertTrue(terrain.gradient_valid.all())
        self.assertTrue(np.all(terrain.max_slope_deg == 0))
        self.assertTrue(np.isnan(terrain.steepest_aspect_deg).all())
        self.assertEqual(terrain.buffered_window.flatten(), (0, 0, 6, 6))
        self.assertEqual((terrain.transform.c + 0.5 * terrain.transform.a,
                          terrain.transform.f + 0.5 * terrain.transform.e), (30, 90))

    def test_known_eastward_rise_yields_westward_aspect(self):
        terrain = self.process(np.tile(np.arange(6) * 10, (6, 1)), (20, 20, 100, 100))
        np.testing.assert_allclose(terrain.max_slope_deg, np.degrees(np.arctan(0.5)), atol=1e-5)
        np.testing.assert_allclose(terrain.steepest_aspect_deg, 270, atol=1e-5)

    def test_slope_uses_ground_distance_instead_of_projected_posting(self):
        north = 3396000 * np.radians(60) + 60
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff", dtype="float32", count=1, height=6, width=6,
                crs=CRS, transform=Affine(20, 0, 0, 0, -20, north),
            ) as dataset:
                populate(dataset, np.tile(np.arange(6) * 10, (6, 1)))
                terrain = prepare_terrain(
                    dataset, band=1, reference=TEST_REFERENCE,
                    bounds_m=(20, north - 100, 100, north - 20), factor=1,
                )
        np.testing.assert_allclose(terrain.max_slope_deg, 45, atol=0.001)

    def test_coarsened_elevation_does_not_smooth_out_native_slope(self):
        values = np.tile([0, 20, 20, 0, 0, 20, 20, 0, 0, 20], (10, 1))
        terrain = self.process(values, (40, 40, 160, 160), factor=2)
        self.assertEqual(terrain.elevation_m.shape, (3, 3))
        np.testing.assert_allclose(terrain.elevation_m, 10)
        np.testing.assert_allclose(terrain.max_slope_deg, np.degrees(np.arctan(0.5)), atol=1e-5)
        self.assertEqual(terrain.transform.a, 40)
        self.assertEqual(terrain.transform.e, -40)

    def test_nodata_and_raster_edges_remain_unsupported(self):
        values = np.zeros((6, 6))
        values[2, 2] = -9999
        terrain = self.process(values, (0, 0, 120, 120))
        self.assertEqual(int(terrain.elevation_valid.sum()), 35)
        self.assertEqual(int(terrain.gradient_valid.sum()), 11)
        self.assertFalse(terrain.gradient_valid[2, 3])
        self.assertFalse(terrain.gradient_valid[0].any())
        self.assertTrue(np.isnan(terrain.elevation_m[2, 2]))
        aggregate = self.process(values, (0, 0, 120, 120), factor=2)
        self.assertTrue(np.isnan(aggregate.elevation_m[1, 1]))
        self.assertFalse(aggregate.elevation_valid[1, 1])

    def test_scales_vertical_values_before_gradient_and_writes_metres(self):
        terrain = self.process(
            np.tile(np.arange(6) * 0.005, (6, 1)), (20, 20, 100, 100),
            reference=replace(TEST_REFERENCE, vertical_unit="km"), scale=2, offset=0.001,
        )
        np.testing.assert_allclose(terrain.elevation_m[0], [11, 21, 31, 41])
        np.testing.assert_allclose(terrain.max_slope_deg, np.degrees(np.arctan(0.5)), atol=1e-5)

    def test_rejects_unaligned_outside_and_incomplete_coarsening(self):
        values = np.zeros((6, 6))
        for bounds, factor, message in [
            ((0, 0, 119, 120), 1, "align"),
            ((-20, 0, 120, 120), 1, "inside"),
            ((0, 0, 100, 120), 2, "multiples"),
        ]:
            with self.subTest(bounds=bounds), self.assertRaisesRegex(IntegrityError, message):
                self.process(values, bounds, factor)

    def test_rejects_westing_and_southing_projected_axes(self):
        with self.assertRaisesRegex(CoordinateError, "easting and northing"):
            validate_crs(CRS + " +axis=wsu", TEST_REFERENCE, require_metric=True)


class PreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.workspace = base / "data"
        self.output = base / "preview"
        source = base / "source.tif"
        with open_raster(
            source, "w", driver="GTiff", dtype="float32", count=1, height=6, width=6,
            crs=CRS, transform=Affine(20, 0, 0, 0, -20, 120), nodata=-9999,
        ) as dataset:
            populate(dataset, np.arange(36).reshape(6, 6))
        spec = {
            "schema_version": 1, "asset_id": "test-terrain", "source_version": "1", "role": "elevation",
            "provider": "Test", "attribution": "Controlled fixture", "access_rights": "Test",
            "entrypoint": source.name, "reference": REFERENCE,
            "members": [{"name": source.name, "uri": source.as_uri(),
                         "expected_sha256": sha256(source.read_bytes()).hexdigest()}],
        }
        (base / "source.json").write_text(json.dumps(spec), encoding="utf-8")
        self.job_config = {
            "schema_version": 1, "region_id": "test-region", "pack_id": "test-preview", "pack_version": "1",
            "capability": "elevation_preview", "source_config": "source.json", "coarsening_factor": 2,
            "aoi": {"version": "1", "crs": "source_native", "bounds_m": [20, 20, 100, 100]},
        }
        self.job_path = base / "job.json"
        self.job_path.write_text(json.dumps(self.job_config), encoding="utf-8")
        self.job = load_job(self.job_path)
        ingest(self.job.source, self.workspace)

    def test_offline_pack_declares_only_preview_capabilities(self):
        manifest = build_preview(self.job, self.workspace, self.output)
        self.assertEqual(manifest["shape"], [2, 2])
        self.assertEqual(manifest["affine"], [40, 0, 20, 0, -40, 100])
        self.assertFalse(manifest["capabilities"]["routing"])
        self.assertEqual({path.name for path in self.output.iterdir()}, {MANIFEST, ELEVATION_PREVIEW})
        self.assertEqual(verify_preview(self.output)["verified_artifacts"], 1)
        with self.assertRaisesRegex(ConfigurationError, "already exists"):
            build_preview(self.job, self.workspace, self.output)

    def test_editing_returned_manifest_does_not_change_preview_policy(self):
        manifest = build_preview(self.job, self.workspace, self.output)
        manifest["capabilities"]["routing"] = True
        manifest["gate_results"]["routing"] = "pass"

        self.assertEqual(verify_preview(self.output)["verified_artifacts"], 1)
        another = build_preview(self.job, self.workspace, self.output.with_name("another"))
        self.assertFalse(another["capabilities"]["routing"])
        self.assertNotIn("routing", another["gate_results"])

    def test_rejects_bad_affine_false_capability_and_missing_or_corrupt_artifact(self):
        manifest = build_preview(self.job, self.workspace, self.output)
        path = self.output / MANIFEST
        for field, value, message in [
            ("vertical_unit", "km", "encoding"),
            ("output_posting_m", [40, 20], "grid"),
            ("affine", [1, 0, 20, 0, -1, 100], "grid"),
            ("capabilities", {**manifest["capabilities"], "routing": True}, "capability"),
        ]:
            with self.subTest(field=field), self.assertRaisesRegex(IntegrityError, message):
                path.write_text(json.dumps({**manifest, field: value}), encoding="utf-8")
                verify_preview(self.output)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        asset = self.output / ELEVATION_PREVIEW
        asset.write_bytes(b"X" * asset.stat().st_size)
        with self.assertRaisesRegex(IntegrityError, "checksum"):
            verify_preview(self.output)
        asset.unlink()
        with self.assertRaisesRegex(IntegrityError, "inventory"):
            verify_preview(self.output)

    def test_job_rejects_claiming_tactical_support(self):
        self.job_path.write_text(json.dumps({**self.job_config, "capability": "routing"}), encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, "supports elevation_preview"):
            load_job(self.job_path)
