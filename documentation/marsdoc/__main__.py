"""Run cell and capability queries from local JSON."""
import argparse
import json
from pathlib import Path

from . import CapabilityQuery, DocumentationEngine, Package, ScoringPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--nside", type=int, default=128)
    parser.add_argument("--policy", type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--cell")
    target.add_argument("--point", nargs=2, type=float, metavar=("LON", "LAT"))
    target.add_argument("--query", type=Path)
    parser.add_argument("--synthetic-context", action="store_true",
                        help="attach a labeled synthetic context result to a cell or point summary")
    args = parser.parse_args()
    if args.synthetic_context and args.query:
        parser.error("--synthetic-context requires --cell or --point")
    try:
        package = Package.model_validate_json(args.package.read_bytes())
        policy = ScoringPolicy.model_validate_json(args.policy.read_bytes()) if args.policy else None
        engine = DocumentationEngine(package, nside=args.nside, policy=policy)
        if args.query:
            result = engine.resolve(CapabilityQuery.model_validate_json(args.query.read_bytes()))
        else:
            cell_id = args.cell or engine.grid.cell_at(args.point).id
            result = engine.summarize(cell_id)
            if args.synthetic_context:
                context = engine.synthetic_context(cell_id)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Invalid evidence input: {error}\n")
    if args.synthetic_context:
        print(json.dumps({"documentation": result.model_dump(mode="json"),
                          "synthetic_science_context": context}, indent=2, allow_nan=False))
    else:
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
