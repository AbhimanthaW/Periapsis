"""Verify the evidence handoff with the repository's schemas and resolver."""
import argparse
import json
from pathlib import Path

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
    schema_path = repo / "documentation" / "schemas"
    package_raw = (handoff / "evidence.json").read_bytes()
    query_raw = (handoff / "evidence-query.json").read_bytes()
    control_query_raw = (handoff / "control-query.json").read_bytes()
    sources = json.loads((handoff / "source-manifest.json").read_bytes())
    validate_schema(schema_path / "evidence-package.v1.schema.json", json.loads(package_raw))
    for raw in (query_raw, control_query_raw):
        validate_schema(schema_path / "capability-query.v1.schema.json", json.loads(raw))
    validate_schema(repo / "contracts" / "source-manifest.v1.schema.json", sources)

    candidate = Package.model_validate_json(package_raw)
    source, = sources["sources"]
    product, = candidate.products
    if (source["id"], source["version"]) != (product.id, product.version):
        raise ValueError("Evidence and source-manifest identities differ")

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
