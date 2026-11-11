from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import ssl
import tempfile
import unittest
from urllib.request import Request

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS

from return_window_pipeline.coordinates import transform_points, validate_crs
from return_window_pipeline.errors import ConfigurationError, CoordinateError, IntegrityError
from return_window_pipeline.ingestion import HTTPSRedirect, acquisition_opener, ingest
from return_window_pipeline.models import SourceSpec, digest
from return_window_pipeline.raster import inspect_observation_support

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/mola-global-4ppd-topography.json"


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.inputs = self.base / "inputs"
        configuration = json.loads(CONFIG.read_text())
        self.configuration = configuration
        for bundle in (Path(os.environ.get("RW_MOLA_WORKSPACE", ROOT / "data")) / "cache/bundles").iterdir():
            if (bundle / configuration["entrypoint"]).is_file():
                shutil.copytree(bundle, self.inputs)
                break
        for member in configuration["members"]:
            member["uri"] = (self.inputs / member["name"]).as_uri()

    def spec(self, *, repin_for_policy_test=False):
        configuration = deepcopy(self.configuration)
        if repin_for_policy_test:
            # Exercise the adapter with trusted-but-contradictory inputs so
            # a checksum mismatch alone cannot make a policy test pass.
            for member in configuration["members"]:
                member["expected_sha256"] = sha256((self.inputs / member["name"]).read_bytes()).hexdigest()
        return SourceSpec.from_dict(configuration)

    def alter(self, filename, before, after):
        path = self.inputs / filename
        original = path.read_bytes()
        self.assertIn(before, original)
        path.write_bytes(original.replace(before, after))
        return original

    def test_mola_preserves_valid_zero_and_distinguishes_missing_from_zero_counts(self):
        record, _, _ = ingest(self.spec(), self.base / "workspace")
        self.assertEqual(record["raster"]["valid_pixels"], 1_036_800)
        self.assertIsNone(record["raster"]["nodata"])
        self.assertEqual(record["raster"]["raw_value_range"], [-8068, 21134])
        support = record["observation_support"]
        self.assertEqual(support["cells_with_observations"], 1_027_663)
        self.assertEqual(support["zero_count_cells"], 9137)
        self.assertEqual(support["missing_count_cells"], 0)
        self.assertTrue(all(record["tool_versions"][key] for key in ("rasterio_gdal", "rasterio_proj", "pyproj_proj")))
        self.assertIn(b"data ignore value = 0", (self.inputs / "megt90n000cb.hdr").read_bytes())
        with rasterio.open(self.inputs / "megt90n000cb.xml") as raster:
            zero = raster.read(1) == 0
            self.assertEqual(zero.sum(), 147)
            self.assertTrue((raster.read_masks(1)[zero] == 255).all())

    def test_mismatched_reference_is_rejected_individually(self):
        for field, value in {
            "frame": "wrong frame", "vertical_reference": "radius from center", "longitude_domain": "-180_180",
            "longitude_direction": "west", "latitude_type": "planetographic",
        }.items():
            with self.subTest(field=field):
                old = self.configuration["reference"][field]
                self.configuration["reference"][field] = value
                try:
                    with self.assertRaises(IntegrityError):
                        ingest(self.spec(), self.base / field)
                finally:
                    self.configuration["reference"][field] = old

    def test_nonzero_prime_meridian_and_west_axis_are_rejected(self):
        for extra in ("+pm=10", "+axis=wnu"):
            with self.subTest(extra=extra), self.assertRaises(CoordinateError):
                validate_crs(f"+proj=longlat +R=3396000 +type=crs {extra}", self.spec().reference)

    def test_transform_rejects_different_same_radius_datum_names(self):
        source = CRS.from_proj4("+proj=longlat +R=3396000 +type=crs")
        target = CRS.from_wkt(source.to_wkt().replace('DATUM["unknown"', 'DATUM["unverified frame"'))
        with self.assertRaisesRegex(CoordinateError, "shared geodetic datum"):
            transform_points(source, target, [(10, 10)], self.spec().reference)

    def test_conflicting_pds4_metadata_is_rejected(self):
        mutations = [
            ("megt", b'>360</cart:east_bounding_coordinate>', b'>350</cart:east_bounding_coordinate>'),
            ("megt", b'>-10668848.651</cart:upperleft_corner_x>', b'>-10668800.000</cart:upperleft_corner_x>'),
            ("megt", b"planetary radius minus the", b"radius from the center and the"),
            ("megt", b"IAU2000_MARS", b"IAU2015_MARS"),
            ("megc", b"IAU2000_MARS", b"IAU2015_MARS"),
            ("megc", b"Positive East", b"Positive West"),
            ("megc", b"SignedMSB2", b"SignedLSB2"),
            ("megc", b"Last Index Fastest", b"First Index Fastest"),
            ("megc", b'</data_type>', b'</data_type><scaling_factor>2</scaling_factor>'),
            ("megc", b'</data_type>', b'</data_type><value_offset>1</value_offset>'),
            ("megc", b'</data_type>', b'</data_type><unit>meter</unit>'),
            ("megc", b'<offset unit="byte">0</offset>', b'<offset unit="byte">2</offset>'),
            ("megc", b'</Element_Array>', b'</Element_Array><Special_Constants><missing_constant>0</missing_constant></Special_Constants>'),
        ]
        for i, (prefix, before, after) in enumerate(mutations):
            filename = prefix + "90n000cb.xml"
            with self.subTest(field=before, prefix=prefix):
                original = self.alter(filename, before, after)
                try:
                    with self.assertRaises(IntegrityError):
                        ingest(self.spec(repin_for_policy_test=True), self.base / f"invalid-{i}")
                finally:
                    (self.inputs / filename).write_bytes(original)

    def test_count_identity_cannot_be_replaced_by_topography(self):
        self.configuration["support_expected_lid"] = self.configuration["expected_lid"]
        with self.assertRaises(IntegrityError):
            ingest(self.spec(), self.base / "wrong-lid")
        self.configuration["support_entrypoint"] = self.configuration["entrypoint"]
        with self.assertRaises(ConfigurationError):
            self.spec()

    def test_generic_count_encoding_is_rejected(self):
        path = self.base / "count.tif"
        crs = "+proj=eqc +R=3396000 +units=m"
        affine = Affine(20, 0, 0, 0, -20, 20)
        grid = {"shape": [1, 2], "crs_wkt": crs, "affine": tuple(affine)[:6]}
        for unit, scale, offset, nodata in [("m", 1, 0, None), (None, 1, 1, None),
                                            (None, 2, 0, None), (None, 1, 0, 0), (None, 1, 0, 1)]:
            with self.subTest(unit=unit, scale=scale, offset=offset, nodata=nodata):
                with rasterio.open(path, "w", driver="GTiff", width=2, height=1, count=1, dtype="int16",
                                   crs=crs, transform=affine, nodata=nodata) as ds:
                    ds.write(np.array([[0, 1]], dtype="int16"), 1)
                    ds.scales, ds.offsets = (scale,), (offset,)
                    if unit:
                        ds.set_band_unit(1, unit)
                with self.assertRaises(IntegrityError):
                    inspect_observation_support(path, grid, self.spec().reference)

    def test_metadata_tampering_and_resealed_interpretation_are_rejected(self):
        spec, workspace = self.spec(), self.base / "workspace"
        record, path, _ = ingest(spec, workspace)
        receipt = sha256(path.read_bytes()).hexdigest()
        self.assertTrue(ingest(spec, workspace, offline=True, expected_record_sha256=receipt)[2])
        for field in ("reference", "raster", "observation_support", "source_specification"):
            with self.subTest(field=field):
                edited = deepcopy(record)
                edited[field]["audit_tamper"] = True
                path.write_text(json.dumps(edited))
                with self.assertRaisesRegex(IntegrityError, "digest mismatch"):
                    ingest(spec, workspace, offline=True)
                del edited["record_sha256"]
                edited["record_sha256"] = digest(edited)
                path.write_text(json.dumps(edited))
                with self.assertRaisesRegex(IntegrityError, "interpretation|pinned specification"):
                    ingest(spec, workspace, offline=True)
        edited = deepcopy(record)
        edited["created_at"] = "2000-01-01T00:00:00Z"
        del edited["record_sha256"]
        edited["record_sha256"] = digest(edited)
        path.write_text(json.dumps(edited))
        with self.assertRaisesRegex(IntegrityError, "trusted handoff receipt"):
            ingest(spec, workspace, offline=True, expected_record_sha256=receipt)

    def test_offline_rejects_legacy_records_and_unlisted_bundle_members(self):
        spec, workspace = self.spec(), self.base / "workspace"
        record, path, _ = ingest(spec, workspace)
        original = path.read_bytes()
        path.write_text('{"source_record_schema_version": 1}')
        with self.assertRaisesRegex(IntegrityError, "Source record v2"):
            ingest(spec, workspace, offline=True)
        path.write_text('{"source_record_schema_version": 2, "other": NaN}')
        with self.assertRaisesRegex(IntegrityError, "Malformed source record"):
            ingest(spec, workspace, offline=True)
        path.write_bytes(original)
        bundle = workspace / "cache/bundles" / record["bundle_sha256"]
        (bundle / "megt90n000cb.xml.aux.xml").write_text("<PAMDataset/>")
        with self.assertRaisesRegex(IntegrityError, "file inventory"):
            ingest(spec, workspace, offline=True)

    def test_tls_keeps_verification_and_refuses_downgrade(self):
        opener = acquisition_opener()
        https = next(handler for handler in opener.handlers if hasattr(handler, "https_open"))
        self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(https._context.check_hostname)
        with self.assertRaisesRegex(IntegrityError, "non-HTTPS redirect"):
            HTTPSRedirect().redirect_request(Request("https://example.org"), None, 302, "", {}, "http://example.org")
