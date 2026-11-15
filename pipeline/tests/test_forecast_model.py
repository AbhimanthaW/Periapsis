"""Tests for the minimal-sensor forecaster. SYNTHETIC data only; nothing here is a skill claim about Mars."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

from return_window_pipeline.forecast.__main__ import main as forecast_main
from return_window_pipeline.forecast.marstime import mars_time
from return_window_pipeline.forecast.model import (Climatology, Prepared, Settings, _blocks, _predict, build_artifact,
                                                   train_and_evaluate)
from return_window_pipeline.forecast.station import StationDataError, ingest_rows, to_grid
from return_window_pipeline.forecast.synthetic import synthetic_rows

ROOT = Path(__file__).resolve().parents[2]
META = {"station_id": "synthetic", "name": "synthetic", "lat_deg": 48.0, "lon_east_deg": -171.85, "provenance": "simulated"}


def _runtime():
    sys.path.insert(0, str(ROOT))
    try:
        from runtime.marswalk import environment, forecast
    except ImportError:  # pragma: no cover
        return None, None
    return environment, forecast


class MarsTimeTests(unittest.TestCase):
    def test_matches_runtime_mars24(self):
        environment, _ = _runtime()
        if environment is None:
            self.skipTest("runtime package not importable")
        for text in ("2021-03-27T19:16:36Z", "2022-01-07T12:00:00Z", "2026-11-15T09:30:00Z"):
            when = datetime.fromisoformat(text.replace("Z", "+00:00"))
            ours = mars_time(when, 77.45)
            sun = environment.mars_sun(text, 18.44, 77.45)
            self.assertAlmostEqual(ours["ls_deg"], sun.solar_longitude_deg, places=6)
            self.assertAlmostEqual(ours["ltst_h"], sun.local_true_solar_time_h, places=6)

    def test_pre_2017_dates_supported(self):
        t = mars_time(datetime(2012, 8, 6, 5, 17, tzinfo=timezone.utc), 137.4)  # Curiosity landing day
        self.assertTrue(140 < t["ls_deg"] < 160)


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_utc_mapping_scale_and_range_rejection(self):
        path = self.dir / "raw.csv"
        path.write_text("UTC,PRESSURE,AIR_TEMP\n2021-03-27T19:16:36Z,7.37,250\n2021-03-27T20:16:36Z,7.40,999\nbad,7.1,240\n")
        rows, report = ingest_rows(path, {"time_utc": "UTC", "pressure_pa": "PRESSURE", "air_temp_k": "AIR_TEMP"},
                                   lon_east=77.45, scale={"pressure_pa": 100.0})
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["pressure_pa"], 737.0)
        self.assertTrue(np.isnan(rows[1]["air_temp_k"]))
        self.assertEqual(report["out_of_range_rejected"]["air_temp_k"], 1)

    def test_local_time_mapping_and_missing_column(self):
        path = self.dir / "viking.csv"
        path.write_text("SOL;BIN_LTST;LS;P;T\n1;0.5;117.0;780.1;190.2\n1;1.5;117.0;781.0;\n")
        rows, _ = ingest_rows(path, {"sol": "SOL", "ltst_h": "BIN_LTST", "ls_deg": "LS", "pressure_pa": "P", "air_temp_k": "T"})
        self.assertEqual([r["sol"] for r in rows], [1.0, 1.0])
        self.assertTrue(np.isnan(rows[1]["air_temp_k"]))
        with self.assertRaises(StationDataError):
            ingest_rows(path, {"sol": "SOL", "ltst_h": "BIN_LTST", "ls_deg": "LS", "wind_ms": "WIND"})


class ForecastModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = to_grid(synthetic_rows(1050), 24, META)
        cls.settings = Settings()
        cls.artifact = build_artifact(cls.grid, cls.settings)

    def test_minimal_kits_selected_and_wind_falls_back(self):
        selected = self.artifact["selection"]
        pressure = selected["pressure_pa"]["6h"]
        self.assertEqual(pressure["kit"], "barometer")
        self.assertEqual(pressure["kit"], pressure["eligible_kits"][0])
        self.assertGreater(pressure["n_test"], 20)
        for key in ("1h", "3h", "6h"):
            self.assertEqual(selected["wind_ms"][key]["status"], "climatology")
        json.dumps(self.artifact, allow_nan=False)

    def test_test_block_cannot_change_kit_selection_or_erase_the_clock(self):
        blocks = _blocks(len(self.grid.sols), self.settings)
        changed = to_grid(synthetic_rows(1050), 24, META)
        changed.values["dust_tau"][blocks == 2] = np.nan
        result = train_and_evaluate(changed, self.settings)
        for horizon, selection in result["selection"]["pressure_pa"].items():
            original = self.artifact["selection"]["pressure_pa"][horizon]
            self.assertEqual(selection["eligible_kits"], original["eligible_kits"])
            self.assertEqual(selection["n_test"], original["n_test"])
            self.assertIn("clock", result["models"]["pressure_pa"][horizon])

    def test_zero_baseline_error_keeps_clock_forecast(self):
        constant = to_grid(synthetic_rows(160), 24, META)
        constant.values["pressure_pa"][:] = 500.0
        result = build_artifact(constant, Settings(horizons_h=(3,)))
        pressure = result["selection"]["pressure_pa"]["3h"]
        self.assertEqual(pressure["kit"], "clock")
        self.assertIsNone(pressure["skill_vs_climatology"])
        self.assertIn("clock", result["models"]["pressure_pa"]["3h"])

    def test_deterministic(self):
        again = build_artifact(to_grid(synthetic_rows(1050), 24, META), self.settings)
        self.assertEqual(self.artifact["model_id"], again["model_id"])

    def test_climatology_ignores_calibration_and_test_blocks(self):
        blocks = _blocks(len(self.grid.sols), self.settings)
        before = Climatology(self.grid, blocks == 0, self.settings).tables["pressure_pa"].copy()
        perturbed = to_grid(synthetic_rows(1050), 24, META)
        perturbed.values["pressure_pa"][blocks != 0] += 500.0
        after = Climatology(perturbed, blocks == 0, self.settings).tables["pressure_pa"]
        np.testing.assert_array_equal(before, after)

    def test_runtime_reproduces_training_predictions(self):
        _, runtime = _runtime()
        if runtime is None:
            self.skipTest("runtime package not importable")
        model = runtime.ForecastModel(self.artifact)
        s = self.settings
        blocks = _blocks(len(self.grid.sols), s)
        clim = Climatology(self.grid, blocks == 0, s)
        p = Prepared(self.grid, clim)
        entry = self.artifact["models"]["pressure_pa"]["3h"]["barometer"]
        h = entry["horizon_bins"]
        from return_window_pipeline.forecast.model import _model_from
        test_k = np.nonzero(blocks[p.sol_index] == 2)[0][100:400:7]
        expected, abstain = _predict(p, "pressure_pa", ("pressure_pa",), h, test_k, _model_from(entry))
        checked = 0
        for k, want, refused in zip(test_k, expected, abstain):
            a = p.anom["pressure_pa"]
            if refused or not np.isfinite(a[k - 2: k + 1]).all() or (k % 24) + h >= 24:
                continue  # keep valid time in the same sol so both sides use the same Ls
            anomalies = {"pressure_pa": {0: a[k], 1: a[k - 1], 2: a[k - 2]}}
            x = runtime._features(("pressure_pa",), "pressure_pa", anomalies, int(k), h, 24, float(p.ls[k]))
            z = (x - np.asarray(entry["mean"])) / np.asarray(entry["scale"])
            climv, _ = model.climatology("pressure_pa", (k + h) % 24, float(p.ls[k + h]))
            got = climv + a[k] + entry["intercept"] + z @ np.asarray(entry["coef"])
            self.assertAlmostEqual(got, want, delta=0.01)
            checked += 1
        self.assertGreater(checked, 10)

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "station.json").write_text(json.dumps(META))
            self.assertEqual(forecast_main(["synth", "--out", str(d / "s.csv"), "--sols", "720"]), 0)
            code = forecast_main(["train", str(d / "s.csv"), "--station", str(d / "station.json"),
                                  "--artifact", str(d / "m.json"), "--report", str(d / "r.md"), "--horizons", "3"])
            self.assertEqual(code, 0)
            self.assertIn("## Selected kit per target and horizon", (d / "r.md").read_text())

    def test_short_record_refuses_unseen_season(self):
        short = to_grid(synthetic_rows(160), 24, META)
        result = train_and_evaluate(short, Settings(horizons_h=(3,)))
        rows = [r for r in result["rows"] if r["target"] == "pressure_pa" and r["kit"] == "barometer"]
        self.assertGreater(rows[0]["abstain_rate"], 0.2)  # test season absent from training -> gate refuses


if __name__ == "__main__":
    unittest.main()
