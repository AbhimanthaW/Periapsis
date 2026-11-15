"""Live hazard map, arrival-time routing and the background monitor."""
from dataclasses import replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from runtime.hazards.live import (HazardLayer, HazardTimeline, LiveFeed, LivePolicy, RadiationAlert,
                                  StormObservation, feed_from_dict, hazard_state, load_feed, storm_at)
from runtime.hazards.monitor import (ACTION_EMERGENCY, ACTION_RETURN_NOW, ARRIVED, CONTINUE, LINK_LOST, REROUTE,
                                     START, Monitor, main, simulate)
from runtime.hazards.route import EMERGENCY, GO, LIVE_CLOSURE, RETURN_NOW, plan_live, route_timeline
from runtime.marswalk import MarswalkError, plan_marswalk
from runtime.marswalk.demo import DEMO_TIME_UTC, demo_inputs
from runtime.marswalk.environment import parse_utc

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
T0 = DEMO_TIME_UTC
START_CELL = (36, 109)


def at(seconds):
    from datetime import timedelta
    return (parse_utc(T0) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def demo():
    baseline, snapshot = demo_inputs(remaining_s=5400)
    return baseline, replace(snapshot, current_cell=START_CELL, tasks=())


def storm(t, centre, *, radius=40.0, v=(0.0, 0.0), wind=24.0, dust=2.5, kind="observed", sid="s1"):
    return StormObservation(sid, at(t), centre, radius, v, wind, dust, kind)


def feed(*storms, layers=(), alerts=()):
    return LiveFeed("test", tuple(storms), tuple(layers), tuple(alerts))


# ------------------------------------------------------------------ the map
def test_storm_footprint_is_on_the_terrain_grid(demo):
    baseline, _ = demo
    support = baseline.support
    state = hazard_state(feed(storm(0, support.center_xy(80, 80), radius=50.0)), support, T0)
    assert state.blocked.shape == support.shape == (160, 160)
    expected = math.pi * 50 ** 2 / (support.cell_dx_m * support.cell_dy_m)
    assert state.blocked.sum() == pytest.approx(expected, rel=0.06)
    assert state.blocked[80, 80] and not state.blocked[80, 92] and not state.radiation_alert


def test_storm_moves_with_its_velocity(demo):
    baseline, _ = demo
    obs = storm(0, (400.0, 400.0), v=(1.0, -0.5))
    assert storm_at(obs, parse_utc(at(120)), LivePolicy()) == (520.0, 340.0)
    assert storm_at(obs, parse_utc(at(10_000)), LivePolicy()) == (400.0 + 1800, 400.0 - 900)   # clamped
    a = hazard_state(feed(obs), baseline.support, at(0))
    b = hazard_state(feed(obs), baseline.support, at(120))
    assert np.argwhere(b.blocked)[:, 1].mean() - np.argwhere(a.blocked)[:, 1].mean() == pytest.approx(24, abs=1)


def test_caution_and_forecast_do_not_block(demo):
    baseline, _ = demo
    centre = baseline.support.center_xy(80, 80)
    caution = hazard_state(feed(storm(0, centre, wind=16.0, dust=0.5)), baseline.support, T0)
    assert not caution.blocked.any() and caution.caution.any()
    forecast = hazard_state(feed(storm(0, centre, kind="forecast")), baseline.support, T0)
    assert not forecast.blocked.any() and forecast.caution.any()


def test_a_live_feed_cannot_see_the_future(demo):
    baseline, _ = demo
    late = storm(300, baseline.support.center_xy(80, 80))
    assert not hazard_state(feed(late), baseline.support, at(400), now_utc=at(100)).blocked.any()
    assert hazard_state(feed(late), baseline.support, at(400), now_utc=at(400)).blocked.any()


def test_stale_storm_holds_its_last_footprint(demo):
    baseline, _ = demo
    obs = storm(0, baseline.support.center_xy(80, 80), v=(2.0, 0.0))
    state = hazard_state(feed(obs), baseline.support, at(900))
    assert state.link_lost and state.stale == ("s1",)
    assert state.blocked[80, 80]                         # held where it was last seen


def test_raster_layers_must_match_the_grid(demo):
    baseline, _ = demo
    support = baseline.support
    wind = np.full(support.shape, 9.08)
    wind[10:20, 10:20] = 25.0
    wind[30, 30] = np.nan
    layer = HazardLayer("wind_speed", wind, support.shape, support.affine, T0)
    state = hazard_state(feed(layers=(layer,)), support, T0)
    assert state.blocked.sum() == 100 and np.isnan(state.wind_mps[30, 30])
    with pytest.raises(MarswalkError) as error:
        feed(layers=(HazardLayer("wind_speed", wind[:-1], (159, 160), support.affine, T0),)).validate(support)
    assert error.value.code == "HAZARD_GRID_MISMATCH"
    shifted = tuple(support.affine[:2]) + (support.affine[2] + 5.0,) + tuple(support.affine[3:])
    with pytest.raises(MarswalkError, match="affine"):
        feed(layers=(HazardLayer("wind_speed", wind, support.shape, shifted, T0),)).validate(support)


def test_latest_observation_reopens_raster_and_forecast_cannot_displace_observation(demo):
    baseline, _ = demo
    support = baseline.support
    old = HazardLayer("wind_speed", np.full(support.shape, 24.0), support.shape, support.affine, T0)
    fresh = replace(old, values=np.full(support.shape, 8.0), observed_utc=at(601))
    raster = hazard_state(feed(layers=(old, fresh)), support, at(601))
    assert not raster.blocked.any() and not raster.link_lost
    point = support.center_xy(80, 80)
    observed = storm(601, point)
    forecast = storm(602, point, wind=9, dust=0, kind="forecast")
    state = hazard_state(feed(observed, forecast), support, at(602))
    assert state.blocked[80, 80] and not state.link_lost
    expired_forecast = hazard_state(feed(forecast), support, at(1300))
    assert not expired_forecast.link_lost and not expired_forecast.blocked.any()


def test_radiation_alert_is_whole_map(demo):
    baseline, _ = demo
    alert = RadiationAlert("sep", at(60), None, at(30))
    assert not hazard_state(feed(alerts=(alert,)), baseline.support, at(30)).radiation_alert
    state = hazard_state(feed(alerts=(alert,)), baseline.support, at(90))
    assert state.radiation_alert and not state.blocked.any()


@pytest.mark.parametrize("bad, message", [
    ({"radius_m": -1}, "radius"),
    ({"kind": "rumour"}, "kind"),
    ({"velocity_mps": [1.0]}, "velocity"),
    ({"observed_utc": "yesterday"}, "UTC"),
])
def test_bad_storm_inputs_are_refused(demo, bad, message):
    baseline, _ = demo
    data = json.loads((EXAMPLES / "live-hazards-dust-devil.json").read_text())
    data["storms"][0].update(bad)
    with pytest.raises(MarswalkError, match=message):
        feed_from_dict(data, baseline.support)


@pytest.mark.parametrize("name", ["dust-devil", "sep", "trapped", "stale"])
def test_example_feeds_load(demo, name):
    baseline, _ = demo
    loaded = load_feed(EXAMPLES / f"live-hazards-{name}.json", baseline.support)
    assert loaded.provenance == "simulated"


# ------------------------------------------------------------------ arrival-time routing
def test_route_avoids_a_storm_where_the_crew_will_be_not_where_it_is(demo):
    baseline, snapshot = demo
    plain = plan_marswalk(baseline, snapshot)
    route = route_timeline(plain.plan("direct_return"), plain.router)
    cell, t = next((c, t) for c, t, _ in route if t > 400)
    support = baseline.support
    obs = storm(0, (support.center_xy(*cell)[0], support.center_xy(*cell)[1] + 0.5 * t), v=(0.0, -0.5))
    assert not hazard_state(feed(obs), support, T0).blocked[cell]          # not there now
    live = plan_live(baseline, snapshot, feed(obs), T0)
    assert live.status == GO and live.plan_id == "direct_return"
    assert cell in live.live_closed
    for c, arrival, _ in live.route:
        assert not live.timeline.hazardous(c, arrival)
    assert live.total_s >= route[-1][1]


def test_hazard_routing_refuses_source_backed_terrain_and_measured_feed(demo):
    baseline, snapshot = demo
    sourced = replace(baseline, support=replace(baseline.support, classification="elevation_preview"))
    with pytest.raises(MarswalkError, match="synthetic terrain"):
        plan_live(sourced, snapshot, feed(), T0)
    measured = replace(storm(0, baseline.support.center_xy(80, 80)), provenance="measured")
    with pytest.raises(MarswalkError, match="simulated and historical replay"):
        plan_live(baseline, snapshot, feed(measured), T0)


def test_live_closures_never_touch_the_terrain_baseline(demo):
    baseline, snapshot = demo
    before = baseline.routable.copy()
    plan_live(baseline, snapshot, load_feed(EXAMPLES / "live-hazards-dust-devil.json", baseline.support), at(300))
    assert np.array_equal(before, baseline.routable) and not baseline.routable.flags.writeable


def test_radiation_alert_forces_return(demo):
    baseline, snapshot = demo_inputs(remaining_s=3600)
    alert = RadiationAlert("sep", at(0), None, at(0))
    live = plan_live(baseline, snapshot, feed(alerts=(alert,)), T0)
    assert live.status == RETURN_NOW and live.plan_id == "direct_return"
    soon = RadiationAlert("sep", at(600), None, at(0))
    live = plan_live(baseline, snapshot, feed(alerts=(soon,)), T0)          # starts during the science trip
    assert live.status == RETURN_NOW and live.plan_id == "direct_return"


def test_forecast_sep_is_advisory_even_in_monitor():
    baseline, snapshot = demo_inputs(remaining_s=3600)
    advisory = RadiationAlert("sep", at(60), None, at(60), kind="forecast")
    monitor = Monitor(baseline, snapshot, feed(alerts=(advisory,)))
    assert monitor.start(T0).plan_id == "science:transect"
    result = monitor.tick(60)
    assert result.action != ACTION_RETURN_NOW and result.plan_id == "science:transect"


def test_short_observed_sep_between_slots_forces_return():
    baseline, snapshot = demo_inputs(remaining_s=3600)
    short = RadiationAlert("sep", at(1), at(5), T0)
    live = plan_live(baseline, snapshot, feed(alerts=(short,)), T0)
    assert live.status == RETURN_NOW and live.plan_id == "direct_return"


def test_one_blocked_shelter_cell_refuses_the_direct_return(demo):
    baseline, snapshot = demo
    support = baseline.support
    values = np.full(support.shape, 8.0)
    values[snapshot.return_cell] = 24.0
    layer = HazardLayer("wind_speed", values, support.shape, support.affine, T0)
    live = plan_live(baseline, snapshot, feed(layers=(layer,)), T0)
    assert live.status == EMERGENCY and live.plan_id is None
    assert live.hold_cell == snapshot.current_cell


def test_storm_on_the_shelter_is_an_emergency_with_a_hold_square(demo):
    baseline, snapshot = demo
    shelter = baseline.support.center_xy(*snapshot.return_cell)
    live = plan_live(baseline, snapshot, feed(storm(0, shelter, radius=160.0)), T0)
    assert live.status == EMERGENCY and live.plan_id is None
    assert live.hold_cell is not None and not live.timeline.blocked[:, live.hold_cell[0], live.hold_cell[1]].any()
    assert any("EMERGENCY" in m for m in live.messages)


def test_live_plan_is_deterministic(demo):
    baseline, snapshot = demo
    f = load_feed(EXAMPLES / "live-hazards-dust-devil.json", baseline.support)
    a = plan_live(baseline, snapshot, f, at(300)).to_dict()
    b = plan_live(baseline, snapshot, f, at(300)).to_dict()
    assert a == b
    json.dumps(a, allow_nan=False)


# ------------------------------------------------------------------ monitor
def test_monitor_warns_then_reroutes_when_the_storm_turns(demo):
    baseline, snapshot = demo
    ticks = simulate(baseline, snapshot, load_feed(EXAMPLES / "live-hazards-dust-devil.json", baseline.support), T0)
    actions = [t.action for t in ticks]
    assert actions[0] == START and actions[-1] == ARRIVED
    reroute = next(t for t in ticks if t.action == REROUTE)
    assert reroute.elapsed_s == 300 and reroute.message.startswith("WARNING")
    assert actions.count(REROUTE) == 1                        # no flip-flopping


def test_monitor_returns_on_radiation_and_on_stale_data():
    baseline, snapshot = demo_inputs(remaining_s=3600)
    sep = simulate(baseline, snapshot, load_feed(EXAMPLES / "live-hazards-sep.json", baseline.support), T0)
    assert [t.action for t in sep][:1] == [START] and ACTION_RETURN_NOW in [t.action for t in sep]
    assert sep[-1].action == ARRIVED
    stale = simulate(baseline, snapshot, load_feed(EXAMPLES / "live-hazards-stale.json", baseline.support), T0)
    lost = next(t for t in stale if t.action == LINK_LOST)
    assert 600 < lost.elapsed_s <= 720 and stale[-1].action == ARRIVED


def test_monitor_holds_in_an_emergency_then_returns(demo):
    baseline, snapshot = demo
    ticks = simulate(baseline, snapshot, load_feed(EXAMPLES / "live-hazards-trapped.json", baseline.support), T0)
    assert ticks[0].action == ACTION_EMERGENCY
    opened = next(t for t in ticks if t.action == ACTION_RETURN_NOW)
    assert all(t.crew_cell == START_CELL for t in ticks if t.elapsed_s < opened.elapsed_s)
    assert ticks[-1].action == ARRIVED


def test_emergency_does_not_jump_to_the_hold_cell(demo):
    baseline, snapshot = demo
    support = baseline.support
    values = np.full(support.shape, 8.0)
    values[snapshot.return_cell] = 24.0
    values[snapshot.current_cell] = 24.0
    layer = HazardLayer("wind_speed", values, support.shape, support.affine, T0)
    monitor = Monitor(baseline, snapshot, feed(layers=(layer,)))
    start = monitor.start(T0)
    assert start.action == ACTION_EMERGENCY
    assert monitor.hold_cell is not None and monitor.hold_cell != START_CELL
    eta = start.remaining_route_s
    assert eta > 0
    assert monitor.tick(eta / 2).crew_cell == START_CELL
    assert monitor.tick(eta + 1).crew_cell == monitor.hold_cell


def test_monitor_preserves_preexisting_completed_tasks():
    baseline, snapshot = demo_inputs(remaining_s=3600)
    completed = tuple(task.id for task in snapshot.tasks)
    monitor = Monitor(baseline, replace(snapshot, completed_task_ids=completed), feed())
    result = monitor.start(T0)
    assert result.plan_id == "direct_return"
    result = monitor.tick(60)
    assert result.plan_id == "direct_return"
    assert monitor._snapshot(result.crew_cell, 60).tasks == ()


def test_monitor_rover_mode(demo):
    baseline, snapshot = demo_inputs(platform="rover", remaining_s=5400)
    snapshot = replace(snapshot, current_cell=START_CELL, tasks=())
    ticks = simulate(baseline, snapshot, load_feed(EXAMPLES / "live-hazards-dust-devil.json", baseline.support), T0)
    assert ticks[-1].action == ARRIVED and ticks[-1].elapsed_s <= 360


def test_cli(capsys):
    assert main([str(EXAMPLES / "live-hazards-dust-devil.json")]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "reroute" in out
    assert main([str(EXAMPLES / "live-hazards-dust-devil.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[-1]["action"] == ARRIVED
