"""Marswalk CLI.

  python -m runtime.marswalk sites
  python -m runtime.marswalk sites --jezero-window /path/to/jezero-elevation.f32
  python -m runtime.marswalk demo
  python -m runtime.marswalk demo --platform rover --rover-fails-at-min 12
  python -m runtime.marswalk demo --weather runtime/examples/weather-wind-warning.json
  python -m runtime.marswalk demo --profile runtime/examples/profile-rover-hypothetical.json
  python -m runtime.marswalk plan contracts/fixtures/synthetic-v1 --closure mid

`sites` runs Phase 0 (evidence, resolution, size and availability gates) on
every terrain-like dataset committed on main and prints the dimensions read
from the data. `demo` needs no pack: it plans a built-in synthetic scenario
before and after a simulated closure. `plan` reads a checked pack v1 with
routing simulation enabled and prints the JSON plan.
"""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

from .config import HumanProfile, snapshot_from_pack
from .environment import PowerScenario
from .errors import MarswalkError
from .plan import plan_marswalk
from .traversability import ScreenPolicy, baseline_from_pack
from .walkback import WalkbackPolicy, breakdown_snapshot


def _profile(args):
    if args.profile is not None:
        from .profiles import load_profile
        profile = load_profile(args.profile)
        if profile.platform != args.platform:
            raise MarswalkError("INVALID_PROFILE", f"--profile is a {profile.platform} profile; "
                                                   f"use --platform {profile.platform}")
        return profile
    if args.platform == "rover":
        from .rover import hypothetical_crew_rover
        return replace(hypothetical_crew_rover(), neighbours=args.neighbours)
    return HumanProfile(pace_model=args.pace_model, pace_scenario=args.pace_scenario, neighbours=args.neighbours)


def _weather(args, snapshot):
    if args.weather is None:
        return snapshot
    from .weather import feed_from_dict
    try:
        data = json.loads(Path(args.weather).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise MarswalkError("INVALID_WEATHER", f"cannot read weather feed {args.weather}: {error}") from error
    time_utc = data.get("now_utc") or snapshot.time_utc
    if time_utc is None:
        raise MarswalkError("INVALID_WEATHER", "weather needs a plan time: give --time-utc or now_utc in the feed")
    return replace(snapshot, weather=feed_from_dict(data), time_utc=time_utc)


def _minutes(value):
    return "      -" if value is None else f"{value / 60:6.1f}m"


def _table(result):
    lines = [f"status {result.status} | recommendation {result.recommendation} | "
             f"backend {result.router.backend} | Dijkstra runs {result.dijkstra_runs}"]
    if result.site_gate is not None:
        d = result.site_gate.dimensions
        lines.append(f"  site: {result.site_gate.status} | {d.rows} x {d.cols} cells at {d.cell_dx_m:g} m "
                     f"({d.width_m / 1000:.2f} x {d.height_m / 1000:.2f} km)")
        vis = result.site_gate.obstacle_visibility
        if vis is not None:
            lines.append(f"  obstacles: {vis['status']} ({vis['detail']})")
    lines.append(f"  {'option':<26}{'total':>9}{'margin':>9}{'energy':>10}  outcome")
    for plan in result.plans:
        e = plan.energy_ledger
        energy = "-" if e is None or e.total_use is None else f"{e.total_use / 3.6e6:.2f}kWh"
        why = "pass" if plan.passed else "; ".join(plan.failure_reasons[:2])
        lines.append(f"  {plan.id:<26}{_minutes(plan.ledger.total_use):>9}{_minutes(plan.ledger.margin):>9}"
                     f"{energy:>10}  {why}")
    if result.walkback is not None:
        walk = result.walkback["walk_home_from_current_s"]
        lines.append(f"  walkback ({result.walkback['policy']['speed_mps']} m/s, "
                     f"{result.walkback['policy']['slope_limit_deg']:g} deg): walk home from here "
                     f"{'impossible' if walk is None else f'{walk / 60:.1f} min'}")
        rec = result.recommendation
        if rec is not None:
            rule = next((r for r in result.plan(rec).constraints if r[0] == "walkback"), None)
            if rule is not None:
                lines.append(f"    {rec}: {rule[2]}")
    if result.weather is not None:
        lines.append(f"  weather ({result.weather.feed_provenance}) at {result.weather.now_utc}:")
        lines += [f"    {message}" for message in result.weather.crew_messages()] or ["    all nominal"]
    env = result.to_dict()["environment"]
    for a in env["activation"]:
        lines.append(f"  environment {a['id']}: {a['status']} ({a['reason']})")
    if env["solar"]["status"] == "computed":
        sun = env["solar"]["sun"]
        lines.append(f"  sun: elevation {sun['elevation_deg']:.1f} deg, azimuth {sun['azimuth_deg']:.0f} deg, "
                     f"Ls {sun['solar_longitude_deg']:.1f}, LTST {sun['local_true_solar_time_h']:.2f} h; "
                     + ", ".join(f"{k} {v}" for k, v in env["solar"]["illumination"].items()))
    return "\n".join(lines)


def _breakdown(result, minutes, args):
    """Simulate a rover failure `minutes` into the recommended plan and replan on foot."""
    from .walkback import _timeline
    rec = result.recommendation
    if rec is None:
        return "  no admissible plan to follow; breakdown not simulated"
    timeline = list(_timeline(result.plan(rec), result.router))
    if not 0 <= minutes * 60 <= timeline[-1][1]:
        raise MarswalkError("INVALID_SNAPSHOT", f"{rec} lasts {timeline[-1][1] / 60:.1f} min; "
                                                f"choose a failure time inside it")
    elapsed = minutes * 60
    cell = timeline[0][0]
    for cell_i, t in timeline:          # last cell reached by the failure time (parked cells included)
        if t > elapsed:
            break
        cell = cell_i
    snapshot = breakdown_snapshot(result.snapshot, cell, elapsed,
                                  policy=WalkbackPolicy(speed_mps=args.walkback_speed_mps))
    walk = plan_marswalk(result.baseline, snapshot, backend=args.backend)
    return (f"ROVER FAILS at {list(cell)} after {elapsed / 60:.1f} min on {rec} (simulated) -> Mode A, walking\n"
            + _table(walk))


def _sites(args):
    from .site import arcadia_gate, healpix_gate, jezero_gate
    window = args.jezero_window or os.environ.get("RW_JEZERO_WINDOW")
    gates = [arcadia_gate(clearance_m=0.35),
             jezero_gate(clearance_m=0.35, window=window, crop=args.crop),
             healpix_gate()]
    try:
        from runtime.mission import load_pack
        from .site import REPO
        pack = load_pack(REPO / "contracts" / "fixtures" / "synthetic-v1", simulation=True)
        from .site import gate_for_support
        gates.insert(0, gate_for_support(baseline_from_pack(pack).support, site_id="synthetic-fixture-v1"))
    except Exception as error:          # the fixture loader needs the locked contracts environment
        print(f"(synthetic fixture skipped: {type(error).__name__}: {error})\n")
    from .demo import demo_inputs
    from .site import gate_for_support
    gates.insert(0, gate_for_support(demo_inputs(closed=False)[0].support, site_id="synthetic-demo",
                                     clearance_m=0.35))
    if args.json:
        print(json.dumps([g.to_dict() for g in gates], allow_nan=False))
        return 0
    print("PHASE 0 - site, evidence and dimensions for every terrain dataset on main\n")
    for g in gates:
        d = g.dimensions
        grid = "index" if d.rows is None else f"{d.rows} x {d.cols}"
        print(f"{g.site_id}: {g.status.upper()}" + ("" if g.code is None else f" ({g.code})"))
        print(f"  grid {grid} = {d.cells:,} cells | cell {d.cell_dx_m:,.1f} x {d.cell_dy_m:,.1f} m | "
              f"native {d.native_spacing_m:,.1f} m" + (f" | {d.note}" if d.note else ""))
        for name, outcome, detail in g.checks:
            print(f"  {name:<10} {outcome:<13} {detail}")
        if g.obstacle_visibility:
            print(f"  obstacles  {g.obstacle_visibility['status']:<13} {g.obstacle_visibility['detail']}")
        if "crop_analysis" in g.data:
            print(f"  real-data crop analysis: {json.dumps(g.data['crop_analysis'])}")
        print()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m runtime.marswalk", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    sites = sub.add_parser("sites", help="Phase 0 gates and dimensions for the datasets on main")
    sites.add_argument("--jezero-window", type=Path, help="pinned Jezero Float32 window (or RW_JEZERO_WINDOW)")
    sites.add_argument("--crop", type=int, nargs=4, metavar=("ROW", "COL", "ROWS", "COLS"),
                       help="analysis crop of the Jezero window (default 462 462 100 100 = 2 x 2 km)")
    sites.add_argument("--json", action="store_true")
    for name in ("plan", "demo"):
        p = sub.add_parser(name)
        if name == "plan":
            p.add_argument("pack", type=Path)
            p.add_argument("--site-sha256")
            p.add_argument("--closure", action="append", default=[])
            p.add_argument("--remaining-s", type=int)
            p.add_argument("--slope-limit-deg", type=float)
            p.add_argument("--power", choices=("battery-only", "demo-solar"))
            p.add_argument("--time-utc")
            p.add_argument("--site-lat-deg", type=float)
            p.add_argument("--site-lon-east-deg", type=float)
            p.add_argument("--horizon-upper-bound-m", type=float)
        else:
            p.add_argument("--png", type=Path)
            p.add_argument("--remaining-s", type=int, default=3600)
            p.add_argument("--rover-fails-at-min", type=float,
                           help="simulate a rover failure this many minutes into the recommended plan")
        p.add_argument("--profile", type=Path, help="human or rover profile JSON (runtime/examples/)")
        p.add_argument("--weather", type=Path, help="weather feed JSON (runtime/examples/weather-*.json)")
        p.add_argument("--walkback-speed-mps", type=float, default=0.75,
                       help="rover walkback walking speed (Apollo emergency walkback average)")
        p.add_argument("--pace-model", choices=("tobler_scaled", "control_linear"), default="tobler_scaled")
        p.add_argument("--pace-scenario", choices=("nominal", "slow"), default="nominal")
        p.add_argument("--neighbours", type=int, choices=(4, 8), default=8)
        p.add_argument("--crew-status", choices=("ok", "issue"), default="ok")
        p.add_argument("--multistop", action="store_true")
        p.add_argument("--alternatives", type=int, default=0)
        p.add_argument("--backend", choices=("auto", "scipy", "python"), default="auto")
        p.add_argument("--platform", choices=("human", "rover"), default="human",
                       help="human = Mode A walking; rover = Mode B driving with walkback")
        p.add_argument("--sep-alert", action="store_true",
                       help="add an explicit SIMULATED solar particle event scenario (return now)")
    args = parser.parse_args(argv)
    try:
        if args.mode == "sites":
            return _sites(args)
        walkback = WalkbackPolicy(speed_mps=args.walkback_speed_mps)
        if args.mode == "plan":
            from runtime.mission import load_pack  # needs the locked contracts environment
            from contracts.pack import PackError
            try:
                pack = load_pack(args.pack, simulation=True, site_sha256=args.site_sha256)
            except PackError as error:
                print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
                return 2
            policy = ScreenPolicy() if args.slope_limit_deg is None else ScreenPolicy(
                policy_id=f"slope-{args.slope_limit_deg:g}deg", slope_limit_deg=args.slope_limit_deg)
            baseline = baseline_from_pack(pack, policy=policy)
            snapshot = snapshot_from_pack(pack, closure_ids=tuple(args.closure), remaining_s=args.remaining_s,
                                          profile=_profile(args), crew_status=args.crew_status)
            from .demo import DEMO_TIME_UTC, demo_power, sep_scenario
            power = None
            if args.platform == "rover" and args.power is None:
                raise MarswalkError("INVALID_POWER", "rover pack planning requires --power")
            if args.power and args.platform != "rover":
                raise MarswalkError("INVALID_POWER", "--power requires --platform rover")
            if args.power == "battery-only":
                power = PowerScenario("none")
            elif args.power == "demo-solar":
                if any(value is None for value in (args.time_utc, args.site_lat_deg, args.site_lon_east_deg)):
                    raise MarswalkError("INVALID_POWER", "demo solar needs explicit time and site coordinates")
                power = replace(demo_power(), horizon_upper_bound_m=args.horizon_upper_bound_m)
            time_utc = args.time_utc or (DEMO_TIME_UTC if args.sep_alert else None)
            snapshot = replace(snapshot, power=power, time_utc=time_utc,
                               site_lat_deg=args.site_lat_deg, site_lon_east_deg=args.site_lon_east_deg,
                               environment=(sep_scenario(snapshot.scenario_id, time_utc),) if args.sep_alert else ())
            snapshot = _weather(args, snapshot)
            result = plan_marswalk(baseline, snapshot, backend=args.backend, multistop=args.multistop,
                                   alternatives_k=args.alternatives, walkback=walkback)
            print(json.dumps(result.to_dict(), allow_nan=False))
            return 0
        from .demo import demo_inputs, plot
        results = []
        for closed in (False, True):
            baseline, snapshot = demo_inputs(closed=closed, remaining_s=args.remaining_s,
                                             pace_scenario=args.pace_scenario, crew_status=args.crew_status,
                                             platform=args.platform, sep_alert=args.sep_alert)
            snapshot = _weather(args, replace(snapshot, profile=_profile(args)))
            results.append(plan_marswalk(baseline, snapshot, backend=args.backend, multistop=args.multistop,
                                         alternatives_k=args.alternatives, walkback=walkback))
        print("SYNTHETIC DEMO - not Mars data\n\nBEFORE closure\n" + _table(results[0]))
        print("\nAFTER closure of the north ramp (simulated field report)\n" + _table(results[1]))
        if args.rover_fails_at_min is not None:
            if args.platform != "rover":
                raise MarswalkError("INVALID_SNAPSHOT", "--rover-fails-at-min needs --platform rover")
            print("\n" + _breakdown(results[1], args.rover_fails_at_min, args))
        if args.png:
            plot(results[0], results[1], args.png)
            print(f"\nwrote {args.png}")
        return 0
    except MarswalkError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
