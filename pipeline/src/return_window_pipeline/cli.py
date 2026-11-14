from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .atlas import build_global_atlas, validate_global_atlas
from .coordinates import normalize_position
from .errors import PipelineError
from .ingestion import ingest, verify_workspace
from .models import SourceSpec
from .regional import build_preview, load_job, verify_preview
from .release import build_atlas_release, verify_atlas_release


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Return Window source ingestion, Mars coordinates and regional previews")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("ingest", help="Acquire, inspect, and register a source bundle")
    acquire.add_argument("configuration", type=Path)
    acquire.add_argument("--workspace", type=Path, required=True)
    acquire.add_argument("--expected-record-sha256", help="Check the exact offline record against a trusted receipt")
    acquisition_mode = acquire.add_mutually_exclusive_group()
    acquisition_mode.add_argument("--offline", action="store_true")
    acquisition_mode.add_argument("--refresh", action="store_true")
    verify = sub.add_parser("verify-cache", help="Recheck every registered member checksum")
    verify.add_argument("--workspace", type=Path, required=True)
    position = sub.add_parser("normalize-position", help="Normalize declared coordinates to planetocentric/east-positive [-180,180)")
    position.add_argument("configuration", type=Path)
    position.add_argument("--longitude", type=float, required=True)
    position.add_argument("--latitude", type=float, required=True)
    preview = sub.add_parser("build-preview", help="Build an offline regional elevation-preview pack")
    preview.add_argument("job", type=Path)
    preview.add_argument("--workspace", type=Path, required=True)
    preview.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify-preview", help="Check an offline elevation-preview pack")
    check.add_argument("directory", type=Path)
    atlas = sub.add_parser("build-global-atlas", help="Build offline elevation and count layers covering all Mars")
    atlas.add_argument("configuration", type=Path)
    atlas.add_argument("--workspace", type=Path, required=True)
    atlas.add_argument("--output", type=Path, required=True)
    atlas.add_argument("--regions", type=Path, required=True, help="Periapsis atlas region catalog JSON")
    atlas_check = sub.add_parser("validate-global-atlas", help="Verify both global layers against pinned MOLA data")
    atlas_check.add_argument("configuration", type=Path)
    atlas_check.add_argument("--workspace", type=Path, required=True)
    atlas_check.add_argument("--directory", type=Path, required=True)
    atlas_check.add_argument("--regions", type=Path, required=True, help="Periapsis atlas region catalog JSON")
    for command, help_text in (
        ("build-atlas-release", "Build and register an offline atlas release candidate"),
        ("verify-atlas-release", "Revalidate an offline atlas release candidate"),
    ):
        release = sub.add_parser(command, help=help_text)
        release.add_argument("configuration", type=Path)
        release.add_argument("--workspace", type=Path, required=True)
        release.add_argument("--regions", type=Path, required=True)
        release.add_argument("--registry", type=Path, required=True)
        release.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            record, path, reused = ingest(
                SourceSpec.load(args.configuration), args.workspace, offline=args.offline,
                refresh=args.refresh, expected_record_sha256=args.expected_record_sha256,
            )
            result = {"record": str(path), "asset_id": record["asset_id"], "source_version": record["source_version"],
                      "bundle_sha256": record["bundle_sha256"], "cache_reused": reused,
                      "preserved_members": len(record["members"]), "raster": record["raster"],
                      "observation_support": record["observation_support"], "gate_results": record["gate_results"]}
        elif args.command == "verify-cache":
            result = {"verified": verify_workspace(args.workspace.resolve())}
        elif args.command == "build-preview":
            manifest = build_preview(load_job(args.job), args.workspace, args.output)
            result = {"pack_id": manifest["pack_id"], "directory": str(args.output.resolve()),
                      "coverage": manifest["coverage"], "capabilities": manifest["capabilities"]}
        elif args.command == "verify-preview":
            result = verify_preview(args.directory)
        elif args.command == "build-global-atlas":
            result = build_global_atlas(SourceSpec.load(args.configuration), args.workspace, args.output,
                                        regions=args.regions)
        elif args.command == "validate-global-atlas":
            result = validate_global_atlas(SourceSpec.load(args.configuration), args.workspace, args.directory,
                                           regions=args.regions)
        elif args.command in {"build-atlas-release", "verify-atlas-release"}:
            release_command = build_atlas_release if args.command == "build-atlas-release" else verify_atlas_release
            result = release_command(args.configuration, args.regions, args.workspace, args.registry, args.version)
        else:
            reference = SourceSpec.load(args.configuration).reference
            lon, lat = normalize_position(args.longitude, args.latitude, reference)
            result = {"longitude_deg": lon, "latitude_deg": lat, "latitude_type": "planetocentric", "longitude_direction": "east", "longitude_domain": "[-180,180)", "frame": reference.frame, "radii_m": [reference.semi_major_m, reference.semi_minor_m]}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (PipelineError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
