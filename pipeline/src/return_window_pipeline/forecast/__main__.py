"""Command line for the minimal-sensor station forecaster.

    python -m return_window_pipeline.forecast ingest SOURCE.csv ... --map pressure_pa=COLUMN ... --station STATION.json --out STATION.csv
    python -m return_window_pipeline.forecast train  STATION.csv --station STATION.json --artifact forecast-model.json --report forecast-report.md
    python -m return_window_pipeline.forecast synth  --out examples/weather/synthetic-station.csv

STATION.json describes the site: {"station_id", "name", "lat_deg", "lon_east_deg", "provenance",
"local_time", "sources": [{"title", "url", "products"}]}. See pipeline/examples/weather/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..errors import PipelineError
from .model import Settings, build_artifact
from .station import VARIABLES, ingest_rows, read_canonical, to_grid, write_canonical
from .synthetic import synthetic_rows


def _pairs(items, kind=str):
    out = {}
    for item in items or []:
        key, _, value = item.partition("=")
        if not value:
            raise PipelineError(f"Expected NAME=VALUE, got {item!r}")
        out[key.strip()] = kind(value.strip())
    return out


def report_markdown(artifact: dict) -> str:
    st = artifact["station"]
    lines = [f"# Forecast evaluation: {st.get('name') or st.get('station_id')}", "",
             f"Model `{artifact['model_id']}` · provenance **{st.get('provenance')}** · "
             f"blocks: {artifact['blocks']['train_sols']} train / {artifact['blocks']['calibration_sols']} calibration / "
             f"{artifact['blocks']['test_sols']} test sols", "",
             "## Selected kit per target and horizon", "",
             "| Target | Horizon | Status | Kit (fewest sensors) | Skill vs climatology | Skill vs best baseline | ML adds? | P10–P90 coverage | Test n |",
             "|---|---|---|---|---:|---:|---|---:|---:|"]
    for target, by_h in artifact["selection"].items():
        for key, sel in by_h.items():
            lines.append(f"| {target} | {key} | {sel['status']} | {sel['kit']} | {_f(sel.get('skill_vs_climatology'))} | "
                         f"{_f(sel.get('skill_vs_best_baseline'))} | {_yn(sel.get('ml_adds_over_best_baseline'))} | "
                         f"{_f(sel.get('coverage_p10_p90'))} | {sel.get('n_test', '')} |")
    lines += ["", "## Every kit and baseline on the common test set", "",
              "| Target | Horizon | Kit | Sensors | MAE | Skill vs climatology | Skill vs best baseline | Coverage | Abstain |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in artifact["rows"]:
        lines.append(f"| {r['target']} | {r['horizon_h']}h | {r['kit']} | {r['sensors']} | {_f(r['mae'])} | "
                     f"{_f(r.get('skill_vs_climatology'))} | {_f(r.get('skill_vs_best_baseline'))} | "
                     f"{_f(r.get('coverage_p10_p90'))} | {_f(r.get('abstain_rate'))} |")
    if artifact.get("transfer"):
        lines += ["", "## Transfer to a second site (corrections reused, climatology refitted locally)", "",
                  "| Target | Horizon | Kit | MAE | Skill vs local climatology | Coverage | Abstain |", "|---|---|---|---:|---:|---:|---:|"]
        for r in artifact["transfer"]:
            lines.append(f"| {r['target']} | {r['horizon_h']}h | {r['kit']} | {_f(r['mae'])} | "
                         f"{_f(r.get('skill_vs_local_climatology'))} | {_f(r.get('coverage_p10_p90'))} | {_f(r.get('abstain_rate'))} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in artifact["limitations"]]
    return "\n".join(lines) + "\n"


def _yn(value):
    return "—" if value is None else ("yes" if value else "no, persistence")


def _f(value):
    return "—" if value is None else f"{value:.3f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m return_window_pipeline.forecast", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ing = sub.add_parser("ingest", help="Map archive CSV columns onto the canonical station table")
    ing.add_argument("sources", nargs="+", type=Path)
    ing.add_argument("--map", action="append", required=True,
                     help="canonical=source column; canonical is time_utc, sol, ltst_h, ls_deg or one of " + ", ".join(VARIABLES))
    ing.add_argument("--scale", action="append", help="variable=factor, e.g. pressure_pa=100 for hPa input")
    ing.add_argument("--station", type=Path, required=True)
    ing.add_argument("--out", type=Path, required=True)
    tr = sub.add_parser("train", help="Fit, validate and select kits; write the model artifact")
    tr.add_argument("station_csv", type=Path)
    tr.add_argument("--station", type=Path, required=True)
    tr.add_argument("--artifact", type=Path, required=True)
    tr.add_argument("--report", type=Path)
    tr.add_argument("--bins", type=int, default=24)
    tr.add_argument("--horizons", default="1,3,6")
    tr.add_argument("--transfer", type=Path, help="Canonical CSV from a second site")
    tr.add_argument("--transfer-station", type=Path)
    sy = sub.add_parser("synth", help="Write the SYNTHETIC example station table")
    sy.add_argument("--out", type=Path, required=True)
    sy.add_argument("--sols", type=int, default=1050)
    sy.add_argument("--seed", type=int, default=20261115)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            station = json.loads(args.station.read_text())
            mapping = _pairs(args.map)
            rows, reports = [], []
            for source in args.sources:
                got, report = ingest_rows(source, mapping, lon_east=station.get("lon_east_deg"), scale=_pairs(args.scale, float))
                rows += got
                reports.append(report)
            digest = write_canonical(args.out, rows)
            result = {"out": str(args.out), "sha256": digest, "rows": len(rows), "files": reports}
        elif args.command == "train":
            station = json.loads(args.station.read_text())
            grid = to_grid(read_canonical(args.station_csv), args.bins, station)
            other = None
            if args.transfer:
                meta = json.loads(args.transfer_station.read_text()) if args.transfer_station else {}
                other = to_grid(read_canonical(args.transfer), args.bins, meta)
            settings = Settings(horizons_h=tuple(int(h) for h in args.horizons.split(",")))
            artifact = build_artifact(grid, settings, transfer=other)
            args.artifact.parent.mkdir(parents=True, exist_ok=True)
            args.artifact.write_text(json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n")
            if args.report:
                args.report.write_text(report_markdown(artifact))
            result = {"artifact": str(args.artifact), "model_id": artifact["model_id"], "selection": artifact["selection"]}
        else:
            digest = write_canonical(args.out, synthetic_rows(args.sols, seed=args.seed))
            result = {"out": str(args.out), "sha256": digest, "provenance": "simulated"}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (PipelineError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
