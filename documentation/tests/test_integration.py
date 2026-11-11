"""Wire compatibility and an archive-verified example."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from marsdoc import CapabilityQuery, DocumentationEngine, Package
from marsdoc.schemas import SCHEMAS, schema_for

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT.parent / "evidence/jezero"


def wire(name, document):
    saved = json.loads((ROOT / "schemas" / f"{name}.v1.schema.json").read_text())
    Draft202012Validator(saved, format_checker=FormatChecker()).validate(document)


@pytest.mark.parametrize("name", SCHEMAS)
def test_schemas_are_current_and_valid(name):
    saved = json.loads((ROOT / "schemas" / f"{name}.v1.schema.json").read_text())
    Draft202012Validator.check_schema(saved)
    assert saved == schema_for(name)


def test_real_jezero_package_and_route_end_to_end():
    evidence = json.loads((EVIDENCE / "jezero-evidence.json").read_text())
    query = json.loads((EVIDENCE / "jezero-route.json").read_text())
    wire("evidence-package", evidence)
    wire("capability-query", query)
    engine = DocumentationEngine(Package.model_validate(evidence))
    atlas = json.loads((ROOT.parent / "web/src/atlas/regions.json").read_text())
    jezero = next(item for item in atlas["regions"] if item["id"] == "43")
    center = jezero["geography"]["center"]
    assert engine.grid.cell_at(center).id == engine.grid.cell_at((center[0] + 360, center[1])).id
    result = engine.resolve(CapabilityQuery.model_validate(query))
    wire("capability-result", result.model_dump(mode="json"))
    assert not result.requested.eligible and result.supported_fallback_ids == ("elevation_20m_posts",)
    assert result.fallbacks[0].variables[0].qualified_fraction == 1
    assert result.provenance[0].product.source_crs.frame == "Mars 2000"
    assert str(result.provenance[0].product.source_url).endswith("M20_JezeroCrater_CTXDEM_20m.tif")
    cell = engine.summarize(engine.grid.cell_at((77.44, 18.45)).id)
    wire("cell-summary", cell.model_dump(mode="json"))
    assert cell.cell.id == "HPX128:96848"
    stereo = next(item for item in cell.modalities if item.modality == "stereo_topography")
    assert stereo.usable_fraction == pytest.approx(.481192, abs=1e-6)
    assert cell.terrain.tier == "Unclassified"
    assert cell.terrain.bounds.upper == pytest.approx(100)


def test_normal_cli_entry_point():
    output = subprocess.check_output([sys.executable, "-m", "marsdoc", str(EVIDENCE / "jezero-evidence.json"),
                                      "--query", str(EVIDENCE / "jezero-route.json")], cwd=ROOT, text=True)
    assert json.loads(output)["supported_fallback_ids"] == ["elevation_20m_posts"]


def test_truthy_strings_and_noninteger_version_are_rejected():
    data = json.loads((EVIDENCE / "jezero-evidence.json").read_text())
    with pytest.raises(ValueError, match="schema_version"):
        Package.model_validate(data | {"schema_version": True})
    data["products"][0]["support_extent_complete"] = "true"
    with pytest.raises(ValueError, match="support_extent_complete"):
        Package.model_validate(data)
