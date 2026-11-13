"""Human Marswalk CLI.

  python -m runtime.marswalk plan contracts/fixtures/synthetic-v1 --closure mid
  python -m runtime.marswalk demo --png marswalk-demo.png

`plan` reads a checked pack v1 with routing simulation enabled and prints the
JSON plan. `demo` needs no pack: it runs a built-in synthetic scenario before
and after a simulated closure and prints a decision table.
"""
import argparse
import json
from pathlib import Path
import sys

from .config import HumanProfile, snapshot_from_pack
from .errors import MarswalkError
from .plan import plan_marswalk
from .traversability import ScreenPolicy, baseline_from_pack


def _profile(args):
    return HumanProfile(pace_model=args.pace_model, pace_scenario=args.pace_scenario, neighbours=args.neighbours)


def _table(result):
    lines = [f"status {result.status} | recommendation {result.recommendation} | "
             f"backend {result.router.backend} | Dijkstra runs {result.router.dijkstra_runs}",
             f"  {'option':<26}{'total':>9}{'margin':>9}  outcome"]
    for plan in result.plans:
        total = plan.ledger.total_use
        margin = plan.ledger.margin
        fmt = lambda v: "      -" if v is None else f"{v / 60:6.1f}m"
        why = "pass" if plan.passed else "; ".join(plan.failure_reasons[:2])
        lines.append(f"  {plan.id:<26}{fmt(total):>9}{fmt(margin):>9}  {why}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m runtime.marswalk", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("plan", "demo"):
        p = sub.add_parser(name)
        if name == "plan":
            p.add_argument("pack", type=Path)
            p.add_argument("--site-sha256")
            p.add_argument("--closure", action="append", default=[])
            p.add_argument("--remaining-s", type=int)
            p.add_argument("--slope-limit-deg", type=float)
        else:
            p.add_argument("--png", type=Path)
            p.add_argument("--remaining-s", type=int, default=3600)
        p.add_argument("--pace-model", choices=("tobler_scaled", "control_linear"), default="tobler_scaled")
        p.add_argument("--pace-scenario", choices=("nominal", "slow"), default="nominal")
        p.add_argument("--neighbours", type=int, choices=(4, 8), default=8)
        p.add_argument("--crew-status", choices=("ok", "issue"), default="ok")
        p.add_argument("--multistop", action="store_true")
        p.add_argument("--alternatives", type=int, default=0)
        p.add_argument("--backend", choices=("auto", "scipy", "python"), default="auto")
    args = parser.parse_args(argv)
    try:
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
            result = plan_marswalk(baseline, snapshot, backend=args.backend, multistop=args.multistop,
                                   alternatives_k=args.alternatives)
            print(json.dumps(result.to_dict(), allow_nan=False))
            return 0
        from .demo import demo_inputs, plot
        results = []
        for closed in (False, True):
            baseline, snapshot = demo_inputs(closed=closed, remaining_s=args.remaining_s,
                                             pace_scenario=args.pace_scenario, crew_status=args.crew_status)
            snapshot = snapshot.__class__(**{**snapshot.__dict__, "profile": _profile(args)})
            results.append(plan_marswalk(baseline, snapshot, backend=args.backend, multistop=args.multistop,
                                         alternatives_k=args.alternatives))
        print("SYNTHETIC DEMO - not Mars data\n\nBEFORE closure\n" + _table(results[0]))
        print("\nAFTER closure of the north ramp (simulated field report)\n" + _table(results[1]))
        if args.png:
            plot(results[0], results[1], args.png)
            print(f"\nwrote {args.png}")
        return 0
    except MarswalkError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
