"""Run cell and capability queries from local JSON."""
import argparse
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
    args = parser.parse_args()
    try:
        package = Package.model_validate_json(args.package.read_bytes())
        policy = ScoringPolicy.model_validate_json(args.policy.read_bytes()) if args.policy else None
        engine = DocumentationEngine(package, nside=args.nside, policy=policy)
        if args.query:
            result = engine.resolve(CapabilityQuery.model_validate_json(args.query.read_bytes()))
        else:
            cell_id = args.cell or engine.grid.cell_at(args.point).id
            result = engine.summarize(cell_id)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Invalid evidence input: {error}\n")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
