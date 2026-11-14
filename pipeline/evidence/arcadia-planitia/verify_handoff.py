"""Verify the handoff files, catalog scope, schemas and resolver decisions."""
import argparse
import json
from pathlib import Path

from handoff_checks import GRID_FILE, read_catalog_searches, ring, verify_checksums

from jsonschema import Draft202012Validator, FormatChecker
from marsdoc import CapabilityQuery, DocumentationEngine, Package


def validate_schema(schema, value):
    Draft202012Validator(json.loads(schema.read_bytes()), format_checker=FormatChecker()).validate(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    handoff, repo = args.handoff, args.repo
    checksums = verify_checksums(handoff)
    searches = read_catalog_searches(handoff / "catalog-search")
    schema_path = repo / "documentation" / "schemas"
    package_raw = (handoff / "evidence.json").read_bytes()
    query_raw = (handoff / "evidence-query.json").read_bytes()
    control_query_raw = (handoff / "control-query.json").read_bytes()
    sources = json.loads((handoff / "source-manifest.json").read_bytes())
    validate_schema(schema_path / "evidence-package.v1.schema.json", json.loads(package_raw))
    for raw, search in zip((query_raw, control_query_raw), searches, strict=True):
        query = json.loads(raw)
        validate_schema(schema_path / "capability-query.v1.schema.json", query)
        if query["geometry"] != {"type": "Polygon", "coordinates": [ring(search["bounds_wsen_deg"])]}:
            raise ValueError(f"Evidence query does not match catalog bounds: {search['response_path']}")
    validate_schema(repo / "contracts" / "source-manifest.v1.schema.json", sources)

    candidate = Package.model_validate_json(package_raw)
    source, = sources["sources"]
    product, = candidate.products
    if (source["id"], source["version"]) != (product.id, product.version):
        raise ValueError("Evidence and source-manifest identities differ")

    if source["window_sha256"] != checksums[GRID_FILE]:
        raise ValueError("Elevation crop does not match the source manifest")

    arcadia = DocumentationEngine(candidate).resolve(CapabilityQuery.model_validate_json(query_raw))
    control = DocumentationEngine(
        Package.model_validate_json((repo / "evidence" / "jezero" / "jezero-evidence.json").read_bytes())
    ).resolve(CapabilityQuery.model_validate_json(control_query_raw))
    if (arcadia.requested.eligible
            or arcadia.requested.variables[0].reason != "no_relevant_product_supplied"
            or arcadia.supported_fallback_ids != ("coarse_elevation_context",)
            or arcadia.fallbacks[0].supporting_product_ids != (product.id,)
            or arcadia.fallbacks[0].variables[0].qualified_fraction != 1
            or not control.requested.eligible
            or control.requested.variables[0].qualified_fraction != 1):
        raise ValueError("Expected scoped CTX refusal, coarse MOLA fallback, and supported control")
    report = {"schemas_validated": True, "arcadia": arcadia.model_dump(mode="json"),
              "well_studied_control": control.model_dump(mode="json")}
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
