"""Forecast service tests on a hand-built model whose numbers can be checked by hand."""
from datetime import timedelta
import math

import pytest

from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import PASS
from runtime.marswalk.forecast import (MARS_HOUR_S, ForecastModel, command_view, crew_view, forecast_messages,
                                       issue_forecast, local_time)
from runtime.marswalk.weather import ADVISORY, WeatherFeed, WeatherStation, assess_weather

NOW = "2026-11-15T09:30:00Z"
LON = 0.0
PRESSURE = [700.0, 710.0, 720.0, 730.0]  # climatology per 6-Mars-hour bin, same in every season


def artifact(ranges=100.0):
    pct = [round((i - 50) / 10, 3) for i in range(1, 100)]            # P10 = -4, P50 = 0, P90 = +4
    wind_pct = [round(-3 + 23 * (i - 1) / 98, 4) for i in range(1, 100)]  # wide upper tail
    names = ["pressure_pa:tendency", "pressure_pa:now_minus_mean3", "sin_target_time", "cos_target_time", "sin_ls", "cos_ls"]
    return {
        "schema_version": 1, "classification": "station_forecast_minimal_sensor", "model_id": "test-model",
        "station": {"station_id": "test", "lon_east_deg": LON, "lat_deg": 0.0, "provenance": "simulated"},
        "time_axis": {"bins_per_sol": 4}, "horizons": {"1h": 1},
        "variables": {"pressure_pa": {"unit": "Pa", "label": "pressure"}, "wind_ms": {"unit": "m/s", "label": "wind speed"}},
        "settings": {"min_gain": 0.02, "tolerance": 0.02, "min_coverage": 0.7},
        "climatology": {"bins": 4, "ls_centers_deg": [0.0, 180.0],
                        "tables": {"pressure_pa": [[v, v] for v in PRESSURE], "wind_ms": [[5.0, 5.0]] * 4},
                        "support": {"pressure_pa": [[0, 0]] * 4, "wind_ms": [[0, 0]] * 4}},
        "models": {
            "pressure_pa": {"1h": {
                "clock": {"sensors": [], "residual_percentiles": pct},
                "barometer": {"sensors": ["pressure_pa"], "base": "anomaly_persistence", "features": names,
                              "mean": [0.0] * 6, "scale": [1.0] * 6, "coef": [0.5, 0, 0, 0, 0, 0], "intercept": 1.0,
                              "ranges": [[-ranges] * 6, [ranges] * 6], "residual_percentiles": pct}}},
            "wind_ms": {"1h": {"clock": {"sensors": [], "residual_percentiles": wind_pct}}}},
        "selection": {"pressure_pa": {"1h": {"status": "model", "kit": "barometer", "sensors": ["pressure_pa"]}},
                      "wind_ms": {"1h": {"status": "climatology", "kit": "clock", "sensors": []}}},
        "rows": [{"target": "pressure_pa", "horizon_h": 1, "kit": "barometer", "skill_vs_climatology": 0.5,
                  "skill_vs_best_baseline": 0.1, "coverage_p10_p90": 0.8, "n": 500},
                 {"target": "pressure_pa", "horizon_h": 1, "kit": "clock", "skill_vs_climatology": 0.0,
                  "skill_vs_best_baseline": -1.0, "coverage_p10_p90": 0.8, "n": 500}],
    }


def observations(anomalies, offsets=(0, 1, 2)):
    """Pressure observations placed in the current bin (0) and the bins before it, anomaly per offset."""
    now = local_time(NOW, LON)
    into_bin = now["local_hours"] - math.floor(now["local_hours"] / 6) * 6  # Mars hours since the bin started
    out = []
    for offset in offsets:
        ago = into_bin / 2 + 6 * offset
        when = (parse_utc(NOW) - timedelta(seconds=ago * MARS_HOUR_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        b = math.floor(local_time(when, LON)["ltst_h"] / 6)
        out.append({"variable": "pressure_pa", "value": PRESSURE[b] + anomalies[offset], "time_utc": when})
    return out


def forecast_of(bundle, target):
    return next(f for f in bundle["forecasts"] if f["target"] == target)


def test_hand_checked_pressure_forecast():
    model = ForecastModel(artifact())
    bundle = issue_forecast(model, observations({0: 4.0, 1: 2.0, 2: 0.0}), NOW)
    f = forecast_of(bundle, "pressure_pa")
    now_bin = math.floor(local_time(NOW, LON)["local_hours"] / 6)
    expected_base = PRESSURE[(now_bin + 1) % 4] + 4.0           # climatology at valid time + current anomaly
    expected_correction = 1.0 + 0.5 * (4.0 - 2.0)              # intercept + coef * tendency
    assert f["status"] == "model" and f["kit"] == "barometer"
    assert f["base"] == pytest.approx(expected_base)
    assert f["correction"] == pytest.approx(expected_correction)
    point = expected_base + expected_correction
    assert (f["p10"], f["p50"], f["p90"]) == pytest.approx((point - 4, point, point + 4))
    assert bundle["sensors_fresh"] == ["barometer"]


def test_missing_previous_bin_falls_back_to_climatology():
    bundle = issue_forecast(ForecastModel(artifact()), observations({0: 4.0}, offsets=(0,)), NOW)
    f = forecast_of(bundle, "pressure_pa")
    assert f["status"] == "climatology" and f["kit"] == "clock"
    assert "missing barometer" in f["reason"]
    assert f["p50"] == pytest.approx(f["climatology"])


def test_out_of_range_inputs_abstain():
    bundle = issue_forecast(ForecastModel(artifact(ranges=0.5)), observations({0: 4.0, 1: 2.0, 2: 0.0}), NOW)
    f = forecast_of(bundle, "pressure_pa")
    assert f["status"] == "abstained" and f["reason"] == "inputs outside the training range"
    assert f["p50"] == pytest.approx(f["climatology"])


def test_forecast_messages_are_advisory_and_never_change_the_plan():
    bundle = issue_forecast(ForecastModel(artifact()), [], NOW)
    wind = forecast_of(bundle, "wind_ms")
    assert wind["p90"] >= 20.0 and wind["chance_at_or_above"]["warning"] >= 0.1
    messages = forecast_messages(bundle, "mast")
    assert [m.variable for m in messages] == ["wind_speed"]
    feed = WeatherFeed(stations=(WeatherStation("mast"),), messages=tuple(messages))
    assessment = assess_weather(feed, NOW)
    assert {a.level for a in assessment.alerts if a.variable == "wind_speed"} == {ADVISORY}
    assert not assessment.return_now
    assert assessment.rule("science")[0] == PASS


def test_crew_view_is_short_and_leads_with_the_warning_chance():
    bundle = issue_forecast(ForecastModel(artifact()), observations({0: 4.0, 1: 2.0, 2: 0.0}), NOW)
    crew = crew_view(bundle, horizon="1h")
    assert crew["level"] == "advisory" and len(crew["lines"]) <= 3
    assert crew["lines"][0].startswith("ADVISORY wind speed") and "Observed values decide" in crew["lines"][0]
    assert crew["lines"][-1].startswith("Forecast from barometer")
    command = command_view(bundle)
    assert command["advisory_flags"] and command["rule"].startswith("Forecasts are advisory")
    assert {r["status"] for r in command["forecasts"]} == {"model", "climatology"}
    assert command["forecasts"][0]["track_record"]["skill_vs_climatology"] == 0.5
