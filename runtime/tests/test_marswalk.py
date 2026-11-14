"""Human Marswalk pipeline (runtime/marswalk). Subsystems 01, 04, 03, 09, 07, 10."""
from dataclasses import replace
from hashlib import sha256
from heapq import heappop, heappush
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from runtime.marswalk import (AuthorizedLimit, HumanProfile, MarswalkError, MissionSnapshot, Router,
                              ScreenPolicy, SurfaceFeature, Task, TerrainGraph, TerrainSupport,
                              ToblerScaled, available_backends, baseline_from_pack, build_baseline,
                              dijkstra, diverse_routes, human_traversal_time, plan_marswalk,
                              route_resource_ledger, snapshot_from_pack)
from runtime.marswalk.demo import demo_inputs
from runtime.marswalk.errors import (FAIL, INSUFFICIENT_TERRAIN_EVIDENCE, LEG_ENDPOINT_EXCLUDED, LEG_NO_EVIDENCE,
                                     LEG_NO_PATH, LEG_OK, LEG_OUT_OF_BOUNDS, NO_RETURN_ROUTE, OK, PASS,
                                     RETURN_OVER_RESERVE, UNKNOWN)
from runtime.marswalk.mobility import ControlLinear
from runtime.marswalk.resources import Phase
from runtime.marswalk.traversability import CELL_NO_DATA, CELL_NO_KERNEL, CELL_PACK_SCREEN, detrended_roughness_m

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "contracts/fixtures/synthetic-v1"
CONTROL = HumanProfile(pace_model="control_linear", neighbours=4)


# ------------------------------------------------------------------ helpers
def grid(z, *, cell=5.0, valid=None, screen=None, policy=ScreenPolicy(), features=(), pack_id="test"):
    z = np.asarray(z, float)
    support = TerrainSupport.from_affine(z.shape, (cell, 0, 0, 0, -cell, z.shape[0] * cell),
                                         native_spacing_m=cell, pack_id=pack_id, pack_version="1")
    valid = np.isfinite(z) if valid is None else valid
    return build_baseline(support, z, valid, screen, policy=policy, features=features)


def snapshot(baseline, current, home, *, tasks=(), remaining_s=3600, reserve_s=0, closures=(),
             profile=HumanProfile(), **extra):
    return MissionSnapshot("m", 1, baseline.support.pack_id, baseline.support.pack_version, "s", current, home, tuple(tasks),
                           extra.pop("completed", ()), remaining_s, reserve_s, tuple(closures), profile, **extra)


def router(baseline, *, pace=ToblerScaled(), neighbours=8, closures=(), backend="auto", scenario="nominal"):
    return Router(TerrainGraph(baseline, pace, neighbours=neighbours, scenario=scenario), closures, backend=backend)


def reference_times(r, source):
    """Textbook Dijkstra over the router's own edge list."""
    adj = {}
    g = r.graph
    for e in r.edge_ids.tolist():
        adj.setdefault(int(g.src[e]), []).append((int(g.dst[e]), float(g.times.seconds[e])))
    dist, heap = {source: 0.0}, [(0.0, source)]
    while heap:
        d, u = heappop(heap)
        if d > dist[u]:
            continue
        for v, w in adj.get(u, []):
            if d + w < dist.get(v, math.inf):
                dist[v] = d + w
                heappush(heap, (d + w, v))
    return dist


# ------------------------------------------------------------------ cross-check with runtime.mission
def _fixture_pack():
    from runtime.mission import load_pack
    return load_pack(FIXTURE, simulation=True, site_sha256=sha256((FIXTURE / "site.json").read_bytes()).hexdigest())


@pytest.mark.parametrize("closures", [(), ("mid",), ("north",), ("mid", "north")])
@pytest.mark.parametrize("remaining", [None, 0, 60, 70, 100, 200])
def test_fixture_control_matches_existing_simulation(closures, remaining):
    from runtime.mission import simulate
    pack = _fixture_pack()
    expected = simulate(pack, closures=list(closures), remaining_s=remaining)
    snap = snapshot_from_pack(pack, closure_ids=closures, remaining_s=remaining, profile=CONTROL)
    result = plan_marswalk(baseline_from_pack(pack), snap)
    assert result.status == expected["status"]
    direct = result.direct_leg
    if expected["direct_return"] is None:
        assert not direct.ok and result.recommendation is None
        return
    assert direct.seconds == expected["direct_return"]["seconds"]
    # equal-time ties may be broken differently; the route must still be valid
    assert direct.cells[0] == snap.current_cell and direct.cells[-1] == snap.return_cell
    assert not set(direct.cells) & set(snap.closure_cells)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(direct.cells, direct.cells[1:]))
    assert result.direct_gate.margin_s == expected["return_margin_s"]
    reverse = result.router.leg_outbound(snap.return_cell, snap.current_cell)
    assert reverse.seconds == expected["reverse_control"]["seconds"]
    if expected["status"] != OK:
        assert result.recommendation is None
        return
    for row in expected["science"]:
        plan = result.plan(f"science:{row['id']}")
        assert plan.ledger.total_use == row["seconds"]
        assert plan.ledger.margin == row["margin_s"]
        assert plan.passed == row["feasible"]
    rec = expected["recommendation"]
    assert result.recommendation == ("direct_return" if rec == "direct_return" else f"science:{rec}")
    assert "science:survey-done" not in [p.id for p in result.plans]       # completed work preserved


def test_fixture_plan_cli():
    out = subprocess.run([sys.executable, "-m", "runtime.marswalk", "plan", str(FIXTURE), "--closure", "mid",
                          "--pace-model", "control_linear", "--neighbours", "4"],
                         cwd=ROOT, text=True, capture_output=True, check=True)
    plan = json.loads(out.stdout)
    assert plan["schema"] == "marswalk-plan-v1"
    assert plan["direct_return"]["seconds"] == 60
    assert plan["recommendation"] == "direct_return"
    assert plan["solver"]["dijkstra_runs"] == 2
    assert "assumed rover or vehicle rescue" in plan["excluded_from_core"]


def test_fixture_unknown_closure_refused():
    with pytest.raises(MarswalkError, match="INVALID_SNAPSHOT"):
        snapshot_from_pack(_fixture_pack(), closure_ids=("nowhere",))


# ------------------------------------------------------------------ 01 mission configuration
def test_snapshot_validation_codes():
    b = grid(np.zeros((4, 4)))
    good = snapshot(b, (0, 0), (3, 3))
    assert good.validate((4, 4)) is good
    cases = {
        "BAD_POSITION": dict(current=(9, 9)),
        "INVALID_UNITS": dict(reserve_s=-1),
        "MIXED_PACK": dict(pack="other"),
        "INVALID_SNAPSHOT": dict(tasks=(Task("a", (1, 1), 5, 1), Task("a", (2, 2), 5, 1))),
        "CONFLICTING_LIMITS": dict(limits=(AuthorizedLimit("max_leg_s", 60, "s", "ops"),
                                           AuthorizedLimit("max_leg_s", 90, "s", "ops"))),
    }
    for code, change in cases.items():
        args = dict(current=(0, 0), reserve_s=0, tasks=(), limits=())
        pack = change.pop("pack", None)
        args.update(change)
        snap = snapshot(b, args.pop("current"), (3, 3), **args)
        with pytest.raises(MarswalkError, match=code):
            snap.validate((4, 4), pack_id=pack)
    with pytest.raises(MarswalkError, match="STALE_REVISION"):
        good.validate((4, 4), expected_revision=2)
    with pytest.raises(MarswalkError, match="INVALID_PROFILE"):
        HumanProfile(platform="rover")
    with pytest.raises(MarswalkError, match="INVALID_PROVENANCE"):
        AuthorizedLimit("x", 1, "s", "ops", provenance="guess")


# ------------------------------------------------------------------ 04 traversal time
def test_traversal_time_is_asymmetric_and_scenario_scales():
    model = ToblerScaled()
    up = human_traversal_time([10.0], [2.0], model=model).seconds[0]
    down = human_traversal_time([10.0], [-2.0], model=model).seconds[0]
    flat = human_traversal_time([10.0], [0.0], model=model).seconds[0]
    assert flat == pytest.approx(20.0)                     # 10 m at 0.5 m/s
    assert up > down and up > flat
    slow = human_traversal_time([10.0], [0.0], model=model, scenario="slow").seconds[0]
    assert slow == pytest.approx(20.0 / 0.7)
    refused = human_traversal_time([10.0, 10.0], [5.0, 1.0], model=ToblerScaled(max_abs_grade=0.3))
    assert math.isinf(refused.seconds[0]) and refused.tag.tolist() == [1, 0]
    assert human_traversal_time([10.0], [3.0], model=ControlLinear()).seconds[0] == 16.0


def test_slow_scenario_keeps_route_and_rescales_time():
    rng = np.random.default_rng(1)
    b = grid(rng.normal(0, 1.5, (25, 25)))
    nominal = router(b).leg_outbound((0, 0), (24, 24))
    slow = router(b, scenario="slow").leg_outbound((0, 0), (24, 24))
    assert slow.cells == nominal.cells
    assert slow.seconds == pytest.approx(nominal.seconds / 0.7)


# ------------------------------------------------------------------ 03 traversability
def test_unknown_kept_separate_from_known_exclusions():
    z = np.zeros((5, 5)); z[0, 0] = np.nan
    screen = np.zeros((5, 5), bool); screen[2, 2] = True
    b = grid(z, screen=screen)
    assert b.reason[0, 0] == CELL_NO_DATA and b.unknown[0, 0] and not b.known_excluded[0, 0]
    assert b.reason[2, 2] == CELL_PACK_SCREEN and b.known_excluded[2, 2] and not b.unknown[2, 2]
    assert b.routable.sum() == 23
    with pytest.raises(ValueError):
        b.routable[1, 1] = False                           # immutable inputs


def test_slope_policy_needs_kernel_support():
    z = np.tile(np.arange(6) * 5.0, (6, 1))                # 45 deg ramp at 5 m cells
    b = grid(z, policy=ScreenPolicy(slope_limit_deg=30))
    assert b.slope_deg[2, 2] == pytest.approx(45.0)
    assert b.known_excluded[1:-1, 1:-1].all()
    assert (b.reason[0, :] == CELL_NO_KERNEL).all() and b.unknown[0, :].all()
    plain = grid(z)                                        # no policy -> no kernel requirement
    assert plain.routable.all()


def test_roughness_is_zero_on_a_plane_and_flags_bumps():
    yy, xx = np.mgrid[0:7, 0:7].astype(float)
    plane = 0.3 * xx - 0.2 * yy
    r = detrended_roughness_m(plane, np.ones((7, 7), bool), 5.0, 5.0)
    assert np.nanmax(r) == pytest.approx(0.0, abs=1e-9)
    bumpy = plane.copy(); bumpy[3, 3] += 2.0
    b = grid(bumpy, policy=ScreenPolicy(roughness_limit_m=0.5))
    assert b.known_excluded[3, 3]


def test_mapped_features_exclude_only_when_authorized():
    flag = SurfaceFeature("dune-1", "dune", ((1, 1),), "ctx-map")
    block = SurfaceFeature("block-1", "boulder", ((2, 2),), "hirise-map", authorized=True)
    b = grid(np.zeros((4, 4)), features=(flag, block))
    assert b.routable[1, 1] and not b.routable[2, 2]
    assert b.flagged == (("dune-1", "dune"),)


# ------------------------------------------------------------------ 09 routing
def test_backends_agree_with_reference():
    rng = np.random.default_rng(7)
    for trial in range(4):
        z = np.cumsum(rng.normal(0, 0.8, (18, 18)), axis=1)
        screen = rng.random((18, 18)) < 0.15
        screen[0, 0] = screen[17, 17] = False
        b = grid(z, screen=screen)
        closures = tuple(map(tuple, np.argwhere(rng.random((18, 18)) < 0.04).tolist()))
        closures = tuple(c for c in closures if c not in ((0, 0), (17, 17)))
        ref = reference_times(router(b, closures=closures), 0)
        for backend in available_backends():
            r = router(b, closures=closures, backend=backend)
            dist, _ = r.outbound_field((0, 0))
            for node, t in ref.items():
                assert dist[node] == pytest.approx(t)
            assert np.isinf(dist[[n for n in range(r.graph.n) if n not in ref]]).all()


def test_return_field_is_time_to_shelter_not_reversed_outbound():
    z = np.tile(np.arange(6) * 1.0, (3, 1))                # rises eastward
    r = router(grid(z))
    home = (1, 0)
    to_home = r.time_to_home(home)
    for cell in [(0, 5), (2, 3), (1, 4)]:
        forward = router(grid(z)).leg_outbound(cell, home)
        assert to_home[cell] == pytest.approx(forward.seconds)
        assert r.leg_return(cell, home).seconds == pytest.approx(forward.seconds)
    assert r.leg_outbound(home, (1, 5)).seconds > r.leg_return((1, 5), home).seconds
    assert r.leg_return((1, 5), home).cells[0] == (1, 5)


def test_no_corner_cutting_and_route_stays_on_allowed_cells():
    screen = np.zeros((2, 2), bool); screen[0, 1] = screen[1, 0] = True
    assert router(grid(np.zeros((2, 2)), screen=screen)).leg_outbound((0, 0), (1, 1)).status == LEG_NO_PATH
    rng = np.random.default_rng(3)
    screen = rng.random((30, 30)) < 0.15
    screen[0, 0] = screen[29, 29] = False
    b = grid(rng.normal(0, 0.3, (30, 30)), screen=screen)
    leg = router(b).leg_outbound((0, 0), (29, 29))
    assert leg.ok
    cells = np.array(leg.cells)
    assert not screen[cells[:, 0], cells[:, 1]].any()
    assert (np.abs(np.diff(cells, axis=0)).max(axis=1) == 1).all()


def test_closure_reroutes_without_mutating_the_baseline_graph():
    b = grid(np.zeros((7, 7)))
    graph = TerrainGraph(b, ToblerScaled())
    base = Router(graph).leg_outbound((3, 0), (3, 6)).seconds
    wall = tuple((r, 3) for r in range(1, 7))
    after = Router(graph, wall).leg_outbound((3, 0), (3, 6))
    assert after.seconds > base and not set(after.cells) & set(wall)
    assert Router(graph).leg_outbound((3, 0), (3, 6)).seconds == base


def test_leg_failure_states_are_distinct():
    z = np.zeros((5, 5)); z[:, 2] = np.nan
    r = router(grid(z))
    assert r.leg_outbound((2, 0), (2, 4)).status == LEG_NO_EVIDENCE        # only unknown cells separate them
    assert r.leg_outbound((2, 0), (2, 4)).cells == ()                       # no path drawn
    assert r.leg_outbound((2, 0), (2, 2)).status == LEG_NO_EVIDENCE
    assert r.leg_outbound((2, 0), (9, 9)).status == LEG_OUT_OF_BOUNDS
    screen = np.zeros((5, 5), bool); screen[:, 2] = True
    wall = router(grid(np.zeros((5, 5)), screen=screen))
    assert wall.leg_outbound((2, 0), (2, 4)).status == LEG_NO_PATH
    assert wall.leg_outbound((2, 0), (2, 2)).status == LEG_ENDPOINT_EXCLUDED


def test_diverse_routes_are_bounded_and_admissible():
    rng = np.random.default_rng(5)
    screen = np.zeros((30, 30), bool); screen[8:22, 12:18] = True
    b = grid(rng.normal(0, 0.4, (30, 30)), screen=screen)
    r = router(b)
    alts = diverse_routes(r, (15, 0), (15, 29), k=3, max_stretch=1.3, max_overlap=0.7)
    assert alts[0].label == "baseline" and len(alts) >= 2
    assert alts[0].leg.seconds == pytest.approx(r.leg_outbound((15, 0), (15, 29)).seconds)
    for alt in alts:
        assert alt.leg.ok and alt.leg.seconds <= 1.3 * alts[0].leg.seconds + 1e-9 and alt.max_overlap <= 0.7 + 1e-9
        cells = np.array(alt.leg.cells)
        assert not screen[cells[:, 0], cells[:, 1]].any()


# ------------------------------------------------------------------ 07 resource budgets
def test_ledger_prefix_and_unknown_values():
    ok = route_resource_ledger([Phase("out", "outbound", 10), Phase("dwell", "dwell", 5),
                                Phase("return", "return", 10)], initial_s=40, reserve_s=10)
    assert ok.check == PASS and ok.margin == 5 and [r.remaining_s for r in ok.rows] == [30, 25, 15]
    over = route_resource_ledger([Phase("out", "outbound", 25), Phase("return", "return", 10)],
                                 initial_s=40, reserve_s=10)
    assert over.check == FAIL and over.margin == -5 and "return" in over.reason
    missing = route_resource_ledger([Phase("out", "outbound", None)], initial_s=40, reserve_s=10)
    assert missing.check == UNKNOWN and missing.margin is None


# ------------------------------------------------------------------ 10 mission optimization
def _corridor_world():
    b = grid(np.zeros((5, 12)))
    tasks = (Task("near", (2, 4), 60, 1, expected_artifact="photo"),
             Task("far", (2, 11), 60, 2, expected_artifact="transect"),
             Task("needs-near", (0, 6), 30, 3, prerequisites=("near",)))
    return b, tasks


def test_selection_priority_then_margin_and_prerequisites():
    b, tasks = _corridor_world()
    result = plan_marswalk(b, snapshot(b, (2, 2), (2, 0), tasks=tasks, remaining_s=600, reserve_s=60))
    assert result.status == OK
    assert result.recommendation == "science:far"                    # priority 2 beats 1; 3 lacks prerequisite
    blocked = result.plan("science:needs-near")
    assert not blocked.passed and any("prerequisites" in r for r in blocked.failure_reasons)
    assert "direct_return" in result.pareto_front or result.plan("direct_return").passed


def test_crew_issue_returns_now_and_limits_apply():
    b, tasks = _corridor_world()
    issue = plan_marswalk(b, snapshot(b, (2, 2), (2, 0), tasks=tasks, remaining_s=600, crew_status="issue"))
    assert issue.recommendation == "direct_return"
    assert all(not p.passed for p in issue.plans if p.kind != "direct_return")
    limited = plan_marswalk(b, snapshot(b, (2, 2), (2, 0), tasks=tasks, remaining_s=600,
                                        limits=(AuthorizedLimit("max_leg_s", 60, "s", "ops"),)))
    assert limited.recommendation == "science:near"                  # far's legs exceed 60 s


def test_gate_statuses_and_unknown_blocks():
    b, tasks = _corridor_world()
    over = plan_marswalk(b, snapshot(b, (2, 11), (2, 0), tasks=tasks, remaining_s=60, reserve_s=30))
    assert over.status == RETURN_OVER_RESERVE and over.recommendation is None
    z = np.zeros((5, 12)); z[:, 6] = np.nan
    gap = grid(z)
    unknown = plan_marswalk(gap, snapshot(gap, (2, 11), (2, 0), tasks=(), remaining_s=600))
    assert unknown.status == INSUFFICIENT_TERRAIN_EVIDENCE and unknown.recommendation is None
    screen = np.zeros((5, 12), bool); screen[:, 6] = True
    wall = grid(np.zeros((5, 12)), screen=screen)
    assert plan_marswalk(wall, snapshot(wall, (2, 11), (2, 0), remaining_s=600)).status == NO_RETURN_ROUTE


def test_multistop_counts_each_dwell_once():
    b, tasks = _corridor_world()
    snap = snapshot(b, (2, 2), (2, 0), tasks=tasks[:2], remaining_s=3600)
    result = plan_marswalk(b, snap, multistop=True)
    pair = result.plan("multi:near>far")
    legs = sum(leg.seconds for _, leg in pair.legs)
    assert pair.ledger.total_use == pytest.approx(legs + 120)
    assert pair.science_value == 3 and pair.passed
    assert result.recommendation.startswith("multi:")


def test_pareto_front_excludes_dominated_plans():
    b, _ = _corridor_world()
    tasks = (Task("a", (2, 4), 60, 1), Task("b", (2, 8), 60, 1))     # same value, b takes longer
    result = plan_marswalk(b, snapshot(b, (2, 2), (2, 0), tasks=tasks, remaining_s=3600))
    assert "science:a" in result.pareto_front and "science:b" not in result.pareto_front
    assert result.recommendation == "science:a"


def test_plan_is_deterministic_and_json_ready():
    baseline, snap = demo_inputs(closed=True)
    first = plan_marswalk(baseline, snap).to_dict()
    second = plan_marswalk(baseline, snap).to_dict()
    assert json.dumps(first, allow_nan=False) == json.dumps(second, allow_nan=False)


def test_demo_closure_flips_the_recommendation():
    before = plan_marswalk(*demo_inputs(closed=False))
    after = plan_marswalk(*demo_inputs(closed=True))
    assert before.recommendation == "science:transect"
    assert after.recommendation == "science:photo-set"
    assert after.plan("science:transect").margin_s < 0 < before.plan("science:transect").margin_s
    assert before.router.dijkstra_runs == after.router.dijkstra_runs == 2


def test_direct_return_hard_limit_blocks_both_return_and_science_recommendations():
    b = grid(np.zeros((5, 5)))
    snap = snapshot(b, (2, 2), (2, 0), tasks=(Task("midpoint", (2, 1), 0, 1),),
                    profile=CONTROL, limits=(AuthorizedLimit("max_leg_s", 5, "s", "ops"),))
    result = plan_marswalk(b, snap)
    assert result.direct_leg.seconds == 10
    assert result.direct_gate.margin_s > 0
    assert result.status == NO_RETURN_ROUTE
    assert result.recommendation is None and result.pareto_front == []
    direct = {rule: outcome for rule, outcome, _ in result.plans[0].constraints}
    science = {rule: outcome for rule, outcome, _ in result.plan("science:midpoint").constraints}
    assert direct["max_leg_s"] == FAIL
    assert science["max_leg_s"] == PASS and science["direct_return_gate"] == FAIL


def test_snapshot_must_match_loaded_pack_version():
    pack = _fixture_pack()
    b = baseline_from_pack(pack)
    snap = snapshot_from_pack(pack, profile=CONTROL)
    assert b.support.pack_version == snap.pack_version
    with pytest.raises(MarswalkError, match="MIXED_PACK"):
        plan_marswalk(b, replace(snap, pack_version="other-version"))
    with pytest.raises(MarswalkError, match="MIXED_PACK"):
        plan_marswalk(replace(b, support=replace(b.support, pack_version=None)), snap)


@pytest.mark.parametrize("args, kwargs", [
    (("unknown", 60, "s", "ops"), {}),
    (("max_leg_s", 60, "ms", "ops"), {}),
    (("max_leg_s", 60, "s", "ops"), {"scope": "outbound"}),
    (("max_leg_s", float("nan"), "s", "ops"), {}),
    (("max_leg_s", float("inf"), "s", "ops"), {}),
    (("max_leg_s", -1, "s", "ops"), {}),
])
def test_unsupported_authorized_limits_are_refused(args, kwargs):
    with pytest.raises(MarswalkError, match="INVALID_LIMIT"):
        AuthorizedLimit(*args, **kwargs)


def test_roughness_requires_support_for_the_full_window():
    b = grid(np.zeros((7, 7)), policy=ScreenPolicy(roughness_limit_m=1, roughness_window=5))
    assert np.isfinite(b.slope_deg[1, 1])
    assert np.isnan(b.roughness_m[1, 1])
    assert b.reason[1, 1] == CELL_NO_KERNEL and not b.routable[1, 1]
    assert b.routable[2, 2]


def test_closed_endpoint_takes_precedence_over_unknown_terrain():
    b = grid(np.zeros((5, 5)), policy=ScreenPolicy(slope_limit_deg=15))
    snap = snapshot(b, (2, 2), (0, 2), closures=(("report", ((2, 2),)),))
    result = plan_marswalk(b, snap)
    assert result.direct_leg.status == LEG_ENDPOINT_EXCLUDED
    assert result.status == NO_RETURN_ROUTE


def test_list_endpoint_coordinates_are_normalized():
    b = grid(np.zeros((5, 5)))
    current, home = [2, 2], [2, 0]
    snap = snapshot(b, current, home, profile=CONTROL)
    current[0] = 99
    home[0] = 99
    assert snap.current_cell == (2, 2) and snap.return_cell == (2, 0)
    assert plan_marswalk(b, snap).recommendation == "direct_return"


def test_published_alternates_respect_full_mission_budget():
    rng = np.random.default_rng(5)
    screen = np.zeros((30, 30), bool)
    screen[8:22, 12:18] = True
    b = grid(rng.normal(0, 0.4, (30, 30)), screen=screen)
    snap = snapshot(b, (15, 0), (15, 0), tasks=(Task("survey", (15, 29), 45, 1),), reserve_s=60)
    key = "science:survey:outbound"

    ample = plan_marswalk(b, snap, alternatives_k=3)
    assert ample.recommendation == "science:survey"
    assert len(ample.alternatives[key]) >= 2
    baseline_use = ample.plan("science:survey").ledger.total_use
    tight = plan_marswalk(b, replace(snap, remaining_s=math.ceil(baseline_use) + snap.reserve_s),
                          alternatives_k=3)
    assert tight.recommendation == ample.recommendation
    assert [alt.label for alt in tight.alternatives[key]] == ["baseline"]

    longest_baseline_leg = max(leg.seconds for _, leg in ample.plan("science:survey").legs)
    limited = plan_marswalk(b, replace(snap, limits=(AuthorizedLimit("max_leg_s", longest_baseline_leg, "s", "ops"),)),
                            alternatives_k=3)
    assert limited.recommendation == ample.recommendation
    assert len(limited.alternatives[key]) < len(ample.alternatives[key])
    assert all(alt.leg.seconds <= longest_baseline_leg for alt in limited.alternatives[key])
