"""Write reproducible JSON Schema from the runtime contract."""
import json
from pathlib import Path

from .contracts import CapabilityQuery, CapabilityResult, CellSummary, Package, ScoringPolicy

SCHEMAS = {
    "evidence-package": Package, "capability-query": CapabilityQuery, "capability-result": CapabilityResult,
    "cell-summary": CellSummary, "scoring-policy": ScoringPolicy,
}


def schema_for(name):
    schema = SCHEMAS[name].model_json_schema()
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}


if __name__ == "__main__":
    folder = Path(__file__).resolve().parents[1] / "schemas"
    for name in SCHEMAS:
        (folder / f"{name}.v1.schema.json").write_text(json.dumps(schema_for(name), indent=2) + "\n")
