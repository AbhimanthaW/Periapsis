import json
from pathlib import Path

import pytest

from runtime.hazards.replay import HazardReplay, PLATFORMS

BUNDLE = Path(__file__).resolve().parents[2] / "web/mission-preview/src/hazards/replay.json"


@pytest.fixture(scope="module")
def bundle():
    return json.loads(BUNDLE.read_text())


def test_bundled_drill_matches_the_router_when_model_is_absent(bundle, tmp_path):
    replay = HazardReplay(tmp_path / "missing-model.json")
    assert replay.model_error
    assert json.loads(json.dumps(replay.terrain)) == bundle["terrain"]
    for offline in bundle["frames"]:
        runtime = json.loads(json.dumps(replay.frame(offline["index"])))
        assert runtime.pop("forecast")["status"] == "unavailable"
        assert runtime == {key: value for key, value in offline.items() if key != "forecast"}


@pytest.mark.parametrize("platform", PLATFORMS)
def test_caution_exclusion_stale_and_recovery(bundle, platform):
    frames = bundle["frames"]
    routes = [frame["routes"][platform] for frame in frames]
    assert routes[0][0]["seconds"] < routes[0][1]["seconds"]
    assert routes[1][0]["exposure_m"] >= 20
    assert routes[1][1]["exposure_m"] == 0
    assert [r["cells"] for r in routes[1]] == [r["cells"] for r in routes[2]]
    assert [r["exposure_m"] for r in routes[1]] == [r["exposure_m"] for r in routes[2]]
    assert routes[3][0]["status"] == "blocked" and routes[3][0]["seconds"] is None
    assert routes[3][1]["status"] == "feasible"
    assert len(frames[3]["footprint"]) > len(frames[1]["footprint"])
    assert frames[4]["footprint"] == frames[3]["footprint"]
    assert frames[4]["weather"]["age_s"] > frames[4]["weather"]["freshness_limit_s"]
    assert routes[4][0]["status"] == "blocked"
    assert frames[4]["weather"]["solar_disabled"]
    assert not frames[5]["footprint"]
    assert routes[5][0]["status"] == routes[5][1]["status"] == "feasible"
    if platform == "human":
        assert routes[3][1]["crew"]["class"] == "GREEN"
    else:
        assert routes[3][1]["energy_margin_wh"] > 0
        assert any(check["id"] == "walkback" and check["status"] == "pass" for check in routes[3][1]["checks"])


def test_forecast_and_observation_keep_source_boundaries(bundle):
    issued = bundle["frames"][0]["forecast"]
    assert issued["status"] == "issued" and issued["station"]["provenance"] == "simulated"
    assert any(row["status"] == "model" for row in issued["rows"])
    assert {"1h", "3h", "6h"} == {row["horizon"] for row in issued["rows"]}
    assert all(row["p10"] <= row["p50"] <= row["p90"] for row in issued["rows"])
    assert not any("chance_at_or_above" in row for row in issued["rows"])
    stale = bundle["frames"][4]["forecast"]
    assert all(row["status"] == "climatology" for row in stale["rows"])
    assert bundle["archive"]["messages"][0]["provenance"] == "historical_replay"
