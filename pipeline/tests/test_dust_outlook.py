"""Fixture tests for the MDAD dust outlook. No real MDAD data is used or shipped here."""
from pathlib import Path
import json
import math
import tempfile
import unittest

import numpy as np

try:
    from scipy.io import netcdf_file
except ImportError:  # pragma: no cover
    netcdf_file = None

from return_window_pipeline.dust.__main__ import main as dust_main
from return_window_pipeline.dust.extract import Region, extract_year, footprints, load_series
from return_window_pipeline.dust.mdad import CANDIDATES, MaskYear, calibrate_convention, convention_by_name
from return_window_pipeline.dust.model import Climatology, Logistic, Settings, build_artifact, build_samples

NLON, NLAT = 360, 181
TRUTH = convention_by_name("east+0_north_down")
SOLS_PER_YEAR = 669


def _blob(grid, convention, lon_c, lat_c, radius_deg, value):
    lons = convention.lon_east_of_index(NLON)
    lats = convention.lat_of_index(NLAT)
    dlon = (lons[:, None] - lon_c + 180) % 360 - 180
    inside = (dlon * np.cos(np.radians(lat_c))) ** 2 + (lats[None, :] - lat_c) ** 2 <= radius_deg ** 2
    grid[inside] = value
    return inside


def _outline(inside, convention):
    edge = inside & ~(np.roll(inside, 1, 0) & np.roll(inside, -1, 0) & np.roll(inside, 1, 1) & np.roll(inside, -1, 1))
    li, ai = np.nonzero(edge)
    return np.column_stack([convention.lon_east_of_index(NLON)[li] % 360, convention.lat_of_index(NLAT)[ai]])


def make_year(directory: Path, my: int, *, rng, mode="approach", sols=range(150, 450), missing_sols=(),
              convention=TRUTH, events_per_season=18):
    """Write MY{my}/MY{my}.nc plus outline CSVs. Storms travel east along 45N in Ls ~180-300."""
    bundle = directory / f"MY{my}"
    bundle.mkdir(parents=True)
    sols = [s for s in sols if s not in missing_sols]
    mask = np.zeros((len(sols), NLON, NLAT), dtype=np.uint8)
    events = []
    for k in range(events_per_season):
        start = int(rng.integers(330, 520))
        if mode == "approach":
            events.append((k + 1, start, float(rng.uniform(-60, -20)), 6.0))  # starts west, moves +6 deg/sol
    names, times = [], []
    for i, sol in enumerate(sols):
        ls = sol * 360.0 / SOLS_PER_YEAR
        names.append(f"S{my}_day{i + 1:02d}")
        times.append([sol - .4, sol + .4, sol, sol, ls - .2, ls + .2, ls, ls])
        frame = mask[i]
        if mode == "noise" and rng.random() < 0.03:  # independent sols: nothing to learn beyond the base rate
            inside = _blob(frame, convention, 0.0, 45.0, 8.0, 1) | _blob(frame, convention, 40.0, 45.0, 4.0, 1)
            np.savetxt(bundle / f"S{my}_day{i + 1:02d}_S{my}_001.csv", _outline(inside, convention), delimiter=",", fmt="%.2f")
        for member, start, lon0, speed in events:
            if start <= sol < start + 10:
                value = member + (133 if member % 5 == 0 else 0)
                inside = _blob(frame, convention, lon0 + speed * (sol - start), 45.0, 7.0, value)
                if sol - start == 2:
                    rows = _outline(inside, convention)
                    suffix = "b" if member % 5 == 0 else ""
                    np.savetxt(bundle / f"S{my}_day{i + 1:02d}_S{my}_{member:03d}{suffix}.csv", rows, delimiter=",", fmt="%.2f")
        holes = rng.random(frame.shape) < 0.02
        frame[holes] = 255
    path = bundle / f"MDAD_MY{my}.nc"
    with netcdf_file(str(path), "w") as nc:
        nc.createDimension("time", len(sols))
        nc.createDimension("lon", NLON)
        nc.createDimension("lat", NLAT)
        nc.createDimension("field", 8)
        nc.createDimension("chars", 12)
        var = nc.createVariable("MDAD", "b", ("time", "lon", "lat"))
        var[:] = mask.view(np.int8)
        t = nc.createVariable("timeList", "d", ("time", "field"))
        t[:] = np.array(times)
        d = nc.createVariable("dayList", "c", ("time", "chars"))
        d[:] = np.array([list(n.ljust(12)) for n in names], dtype="S1")
    return bundle


REGIONS = [Region("90", "Target", 0.0, 45.0), Region("91", "South", 0.0, -30.0), Region("92", "Dateline", 179.5, 45.0)]


def write_regions(path: Path):
    path.write_text(json.dumps({"regions": [{"id": r.id, "name": r.name, "geography": {"center": [r.lon_east, r.lat]}}
                                            for r in REGIONS]}))


@unittest.skipIf(netcdf_file is None, "scipy is required to write NetCDF fixtures")
class DustOutlookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="return-window-dust-")
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_outline_check_recovers_non_default_convention(self):
        bundle = make_year(self.dir, 29, rng=np.random.default_rng(1), sols=range(320, 420))
        with MaskYear(bundle / "MDAD_MY29.nc") as year:
            self.assertEqual((year.nlon, year.nlat, year.year), (NLON, NLAT, 29))
            result = calibrate_convention(year, sorted(bundle.glob("*.csv")))
        self.assertEqual(result["best"], TRUTH.name)
        self.assertTrue(result["accepted"])
        self.assertGreater(result["scores"][TRUTH.name], 0.9)
        self.assertTrue(all(score < 0.5 for name, score in result["scores"].items() if name != TRUTH.name))

    def test_extraction_counts_missing_split_and_duplicate_sols(self):
        bundle = self.dir / "MY30"
        bundle.mkdir()
        mask = np.zeros((3, NLON, NLAT), dtype=np.uint8)
        region = Region("x", "x", 10.0, 0.0)
        prints = footprints(region, TRUTH, NLON, NLAT, 200.0, 600.0)
        li, ai = prints["core"]
        mask[0, li[:2], ai[:2]] = 140   # splitting member counts as storm
        mask[0, li[2:3], ai[2:3]] = 255  # missing is neither valid nor storm
        mask[1, li[2:3], ai[2:3]] = 7    # distinct storm pixel in the same sol
        mask[2, li, ai] = 255
        with netcdf_file(str(bundle / "MY30.nc"), "w") as nc:
            nc.createDimension("time", 3); nc.createDimension("lon", NLON); nc.createDimension("lat", NLAT)
            nc.createDimension("field", 8)
            lon = nc.createVariable("lon", "d", ("lon",))
            lon.units = "degrees east"
            lon[:] = np.arange(NLON) * (360.0 / NLON)
            lat = nc.createVariable("lat", "d", ("lat",))
            lat.units = "degrees north"
            lat[:] = TRUTH.lat_of_index(NLAT)
            nc.createVariable("MDAD", "b", ("time", "lon", "lat"))[:] = mask.view(np.int8)
            nc.createVariable("timeList", "d", ("time", "field"))[:] = np.array(
                [[10, 10, 10.2, 10, 5, 5, 5, 5], [10, 10, 9.9, 10, 5, 5, 5, 5], [11, 11, 11, 11, 6, 6, 6, 6]])
        with MaskYear(bundle / "MY30.nc") as year:
            self.assertEqual(year.convention, TRUTH)
            out = extract_year(year, [region], year.convention, core_km=200.0, ring_km=600.0)
        total = len(li)
        np.testing.assert_array_equal(out["sol"], [10, 11])
        self.assertEqual(out["duplicate_sols"], 1)
        np.testing.assert_array_equal(out["counts"][0, 0, :2], [total, 3])  # union over the two records of sol 10
        np.testing.assert_array_equal(out["counts"][1, 0, :2], [0, 0])
        self.assertEqual(out["core_total"][0], total)

    def test_footprint_wraps_the_dateline(self):
        prints = footprints(REGIONS[2], TRUTH, NLON, NLAT, 300.0, 900.0)
        lons = TRUTH.lon_east_of_index(NLON)[prints["core"][0]]
        self.assertTrue((lons > 170).any() and (lons < -170).any())

    def test_logistic_matches_reference_solution(self):
        rng = np.random.default_rng(3)
        x = rng.normal(size=(2000, 4))
        y = (rng.random(2000) < 1 / (1 + np.exp(-(x @ [1.5, -1.0, 0.5, 0.0] + 0.3)))).astype(float)
        model = Logistic().fit(x, y, l2=1.0)
        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError:
            self.skipTest("scikit-learn not installed")
        z = (x - model.mean) / model.scale
        reference = LogisticRegression(C=1.0, tol=1e-10, max_iter=1000).fit(z, y)
        np.testing.assert_allclose(model.coef[1:], reference.coef_[0], atol=1e-4)
        np.testing.assert_allclose(model.coef[0], reference.intercept_[0], atol=1e-4)

    def _pipeline(self, mode):
        rng = np.random.default_rng(7)
        bundles = [make_year(self.dir / mode, my, rng=rng, mode=mode, missing_sols=range(400, 405) if my == 29 else ())
                   for my in (28, 29, 30, 31)]
        regions = self.dir / f"{mode}-regions.json"
        write_regions(regions)
        series = self.dir / f"{mode}-series"
        code = dust_main(["extract", *map(str, bundles), "--regions", str(regions), "--output", str(series),
                          "--core-km", "300", "--ring-km", "1500"])
        self.assertEqual(code, 0)
        return load_series(series)

    def test_model_beats_climatology_when_storms_approach(self):
        series = self._pipeline("approach")
        self.assertEqual(series["manifest"]["grid"]["convention"]["name"], TRUTH.name)
        settings = Settings(horizon_sols=3, min_bin_samples=5)
        artifact = build_artifact(series, settings, with_sensitivity=False)
        pooled = artifact["validation"]["pooled"]
        self.assertEqual(artifact["status"], "model_skilful", pooled)
        self.assertEqual(artifact["source_review"], {"status": "qualified", "unverified_mars_years": []})
        self.assertGreater(pooled["brier_skill_score"], 0.05)
        target = artifact["regions"]["90"]
        peak = max(range(12), key=lambda i: target["climatology"][i] or 0)
        self.assertGreater(target["nearby"][peak], target["quiet"][peak])
        json.dumps(artifact, allow_nan=False)
        again = build_artifact(series, settings, with_sensitivity=False)
        self.assertEqual(artifact["artifact_id"], again["artifact_id"])

    def test_source_disagreement_withholds_even_a_skilful_artifact(self):
        series = self._pipeline("approach")
        receipt = series["manifest"]["grid"]["calibration"][0]
        receipt.update(basis="embedded_netcdf_coordinates", outline_agrees=False)
        artifact = build_artifact(series, Settings(horizon_sols=3), with_sensitivity=False)

        self.assertEqual(artifact["status"], "model_skilful")
        self.assertEqual(artifact["source_review"], {
            "status": "withheld", "unverified_mars_years": [receipt["mars_year"]]})
        self.assertEqual(artifact["regions"], {})

    def test_gate_withholds_model_without_signal(self):
        series = self._pipeline("noise")
        artifact = build_artifact(series, Settings(horizon_sols=3, min_bin_samples=5), with_sensitivity=False)
        self.assertEqual(artifact["status"], "climatology_only", artifact["validation"]["pooled"])
        self.assertNotIn("nearby", artifact["regions"]["90"])

    def test_climatology_ignores_held_out_year(self):
        series = self._pipeline("approach")
        settings = Settings(horizon_sols=3)
        samples = build_samples(series, settings)
        train = samples.year != 31
        before = Climatology(samples, train, 3, settings).p.copy()
        samples.y[samples.year == 31] = 1 - samples.y[samples.year == 31]
        np.testing.assert_array_equal(before, Climatology(samples, train, 3, settings).p)

    def test_extract_rejects_contradicting_convention(self):
        rng = np.random.default_rng(2)
        bundle = make_year(self.dir, 30, rng=rng, sols=range(320, 380))
        regions = self.dir / "r.json"
        write_regions(regions)
        wrong = next(c.name for c in CANDIDATES if c.name != TRUTH.name)
        code = dust_main(["extract", str(bundle), "--regions", str(regions), "--output", str(self.dir / "o"),
                          "--convention", wrong])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
