"""Command line for the MDAD dust outlook.

    python -m return_window_pipeline.dust inspect   BUNDLE...
    python -m return_window_pipeline.dust extract   BUNDLE... --regions REGIONS.json --output SERIES_DIR
    python -m return_window_pipeline.dust train     SERIES_DIR --artifact dust-outlook.json

A BUNDLE is one extracted MDAD v1.1 Mars-year archive (for example ``MY29/`` from ``MY29.tar.gz``).
It must contain exactly one ``.nc`` mask file; its storm-outline ``.csv`` files are used to verify the
grid convention.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..errors import PipelineError
from .extract import extract_year, load_regions, load_series, write_series
from .mdad import CANDIDATES, CSV_PATTERN, DustDataError, MaskYear, calibrate_convention, convention_by_name
from .model import Settings, build_artifact


def _bundle(path: Path) -> tuple[Path, list[Path]]:
    if path.is_file() and path.suffix == ".nc":
        return path, sorted(p for p in path.parent.rglob("*.csv") if CSV_PATTERN.search(p.name))
    masks = sorted(path.rglob("*.nc"))
    if len(masks) != 1:
        raise DustDataError(f"{path} must contain exactly one .nc mask file, found {len(masks)}")
    return masks[0], sorted(p for p in path.rglob("*.csv") if CSV_PATTERN.search(p.name))


def _convention_check(year, csvs):
    # Embedded axes identify the raster's coordinates directly. Keep outline
    # disagreements in the receipt for independent source review.
    if year.convention is None:
        return calibrate_convention(year, csvs)
    entry = {"mars_year": year.year, "basis": "embedded_netcdf_coordinates", "best": year.convention.name,
             "accepted": True}
    if csvs:
        try:
            outline = calibrate_convention(year, csvs)
            entry["outline_check"] = outline
            entry["outline_agrees"] = outline["accepted"] and outline["best"] == year.convention.name
        except DustDataError as error:
            entry["outline_agrees"] = False
            entry["outline_error"] = str(error)
    return entry


def _choose_convention(calibrations: list[dict], forced: str | None):
    accepted = {c["best"] for c in calibrations if c["accepted"]}
    if forced:
        convention = convention_by_name(forced)
        if accepted and accepted != {forced}:
            raise DustDataError(f"--convention {forced} contradicts the outline check or embedded axes {sorted(accepted)}")
        return convention
    if len(accepted) != 1 or not all(c["accepted"] for c in calibrations):
        raise DustDataError("Grid convention not established for every year: "
                            + json.dumps([{k: c[k] for k in ("mars_year", "best", "accepted")} for c in calibrations]))
    return convention_by_name(accepted.pop())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m return_window_pipeline.dust", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Print MDAD file headers and the grid-convention check")
    inspect.add_argument("bundles", nargs="+", type=Path)
    extract = sub.add_parser("extract", help="Extract per-region daily storm coverage")
    extract.add_argument("bundles", nargs="+", type=Path)
    extract.add_argument("--regions", type=Path, required=True, help="web/src/atlas/regions.json")
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--core-km", type=float, default=100.0)
    extract.add_argument("--ring-km", type=float, default=800.0)
    extract.add_argument("--convention", choices=[c.name for c in CANDIDATES],
                         help="Only if the outline check cannot run; it must agree with any accepted check")
    train = sub.add_parser("train", help="Validate the model and write the browser artifact")
    train.add_argument("series", type=Path)
    train.add_argument("--artifact", type=Path, required=True)
    train.add_argument("--horizon-sols", type=int, default=Settings.horizon_sols)
    train.add_argument("--storm-fraction", type=float, default=Settings.storm_fraction)
    train.add_argument("--no-sensitivity", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = []
            for bundle in args.bundles:
                mask, csvs = _bundle(bundle)
                with MaskYear(mask) as year:
                    entry = {"header": year.header(), "outline_csv_files": len(csvs)}
                    if csvs or year.convention:
                        entry["convention_check"] = _convention_check(year, csvs)
                    result.append(entry)
        elif args.command == "extract":
            regions, regions_sha = load_regions(args.regions)
            opened = [(_bundle(b), b) for b in args.bundles]
            calibrations = []
            for (mask, csvs), _ in opened:
                with MaskYear(mask) as year:
                    if csvs or year.convention:
                        calibrations.append(_convention_check(year, csvs))
                    elif not args.convention:
                        raise DustDataError(f"{mask.name}: no outline CSVs; cannot verify the grid convention")
            convention = _choose_convention(calibrations, args.convention)
            years = {}
            for (mask, _), _ in opened:
                with MaskYear(mask) as year:
                    if year.year in years:
                        raise DustDataError(f"Mars year {year.year} supplied twice")
                    years[year.year] = extract_year(year, regions, convention, core_km=args.core_km, ring_km=args.ring_km)
                    print(f"MY{year.year}: {len(years[year.year]['sol'])} sols", file=sys.stderr)
            manifest = write_series(args.output, regions, regions_sha, years, convention, calibrations,
                                    [m for (m, _), _ in opened], core_km=args.core_km, ring_km=args.ring_km)
            result = {"output": str(args.output.resolve()), "convention": convention.name, "years": manifest["years"]}
        else:
            settings = Settings(horizon_sols=args.horizon_sols, storm_fraction=args.storm_fraction)
            artifact = build_artifact(load_series(args.series), settings, with_sensitivity=not args.no_sensitivity)
            args.artifact.parent.mkdir(parents=True, exist_ok=True)
            args.artifact.write_text(json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n")
            result = {"artifact": str(args.artifact.resolve()), "artifact_id": artifact["artifact_id"],
                      "status": artifact["status"], "pooled": artifact["validation"]["pooled"],
                      "folds": artifact["validation"]["folds"]}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (PipelineError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
