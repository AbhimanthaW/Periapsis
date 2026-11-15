from dataclasses import replace

import numpy as np
import pytest

from runtime.humancost import load_crew, load_policy
from runtime.humancost.calculator import _use
from runtime.hazards.live import StormObservation
from runtime.hazards.timing import StormTiming
from runtime.marswalk import HumanProfile, plan_marswalk
from runtime.marswalk.calibration import validate_traverses
from runtime.marswalk.demo import DEMO_TIME_UTC
from runtime.marswalk.environment import parse_utc
from runtime.marswalk.mobility import TAG_OK, TAG_REFUSED_GRADE, ToblerScaled
from runtime.marswalk.profiles import profile_to_dict
from runtime.marswalk.rover import RoverMobility, drive_cost
from runtime.marswalk.routing import SearchCache, TerrainGraph
from runtime.tests.test_marswalk_rover_env import grid, rover, snapshot
from runtime.tests.tradeoff_world import CREW, POLICY


def test_crossing_can_clear_outbound_and_fail_at_dwell_or_return():
    support = grid(np.zeros((7, 9))).support
    x, y = support.center_xy(3, 4)
    storm = StormObservation("crossing", DEMO_TIME_UTC, (x, y + 40), 2, (0, -.2), 24, 2.4)
    timing = StormTiming(support, parse_utc(DEMO_TIME_UTC), (storm,))
    path = [(3, 3), (3, 4), (3, 5)]
    assert timing.clear(path, (0, 20, 40))
    assert not timing.clear(path[::-1], (180, 200, 220))
    assert not timing.clear([(3, 4), (3, 4)], (20, 220))
    assert not timing.clear(path, (1800, 1820, 1840))  # swept fallback past valid projection


def test_slower_lower_climb_route_can_meet_a_resource_limit():
    z = np.zeros((7, 15))
    z[3, 6:9] = 2
    baseline = grid(z)
    state = snapshot(baseline, (3, 1), (3, 13), profile=HumanProfile(pace_model="control_linear", neighbours=4))
    fastest = plan_marswalk(baseline, state).direct_leg

    def below_consumption_limit(option):
        # Uniform cost in seconds equivalent, for this fixture's resource.
        leg = option.legs[0][1]
        return leg.seconds + 10 * leg.ascent_m <= 75

    result = plan_marswalk(baseline, state, constrained_search=True, alternative_preference=below_consumption_limit)
    assert result.direct_leg.seconds > fastest.seconds
    assert result.direct_leg.ascent_m < fastest.ascent_m
    assert below_consumption_limit(result.plans[0])
    assert result.plans[0].alternative_search["status"] == "found"


def test_search_cache_reuses_shelter_field_and_invalidates_on_closure():
    baseline = grid(np.zeros((7, 13)))
    state = snapshot(baseline, (3, 1), (3, 11), profile=HumanProfile(pace_model="control_linear", neighbours=4))
    cache = SearchCache(baseline)
    first = plan_marswalk(baseline, state, search_cache=cache)
    repeat = plan_marswalk(baseline, replace(state, revision=2), search_cache=cache)
    closed = plan_marswalk(baseline, replace(state, revision=3, closures=(("storm", ((3, 6),)),)), search_cache=cache)
    assert first.direct_leg == repeat.direct_leg
    assert repeat.router.dijkstra_runs == 0 < first.router.dijkstra_runs
    assert closed.direct_leg.seconds > repeat.direct_leg.seconds
    assert (3, 6) not in closed.direct_leg.cells


def test_rover_cross_slope_and_held_out_slip_use_the_same_mobility():
    baseline = grid(np.broadcast_to(np.arange(7)[:, None] * .25, (7, 7)))
    p = rover(max_cross_slope_deg=2.0, drive_slip_fraction=.20)
    graph = TerrainGraph(baseline, RoverMobility(p), neighbours=4)
    tags = dict(zip(zip(graph.src, graph.dst), graph.times.tag))
    assert tags[(24, 25)] == TAG_REFUSED_GRADE
    assert tags[(24, 31)] == TAG_OK

    expected_t, energy = drive_cost(p, 15, 0)
    row = {"horizontal_m": 15, "dz_m": 0, "elapsed_s": float(expected_t), "wheel_speed_mps": p.nominal_speed_mps,
           "drive_energy_j": float(energy)}
    data = {"source": "deliberate simulation control", "classification": "simulated",
            "profile": profile_to_dict(replace(p, drive_slip_fraction=0)),
            "segments": [row | {"group": "first", "split": "fit"}, row | {"group": "second", "split": "holdout"}]}
    result = validate_traverses(data)
    assert result["fitted_profile"]["drive_slip_fraction"] == pytest.approx(.20)
    assert result["holdout"]["drive_energy_j"]["mean_absolute_error"] < 1e-6
    data["segments"][1]["group"] = "first"
    with pytest.raises(ValueError, match="overlaps"):
        validate_traverses(data)


def test_walking_fit_and_oxygen_are_scored_on_another_traverse():
    crew, policy = load_crew(CREW), load_policy(POLICY)
    walker = next(person for person in crew.astronauts if person.id != crew.reference_id)
    measured_s = float(ToblerScaled(v_flat_mps=.6).seconds(30, 3))
    measured_o2 = _use(walker, policy, measured_s, 3)[0]["oxygen"]
    data = {"source": "deliberate simulation control", "classification": "simulated",
            "profile": profile_to_dict(HumanProfile()), "segments": [
                {"group": "flat", "split": "fit", "horizontal_m": 30, "dz_m": 0, "elapsed_s": 50},
                {"group": "slope", "split": "holdout", "horizontal_m": 30, "dz_m": 3, "elapsed_s": measured_s,
                 "oxygen_g": measured_o2, "astronaut_id": walker.id},
            ]}
    result = validate_traverses(data, crew=crew, policy=policy)
    assert result["fitted_profile"]["v_flat_mps"] == pytest.approx(.6)
    assert result["holdout"]["time_s"]["mean_absolute_error"] < 1e-9
    assert result["holdout"]["oxygen_g"]["mean_absolute_error"] < 1e-9
