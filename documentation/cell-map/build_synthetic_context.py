"""Export a labeled HEALPix science fixture separately from real cell records."""
from hashlib import sha256
import json
from pathlib import Path

from marsdoc import DocumentationEngine, Package
from marsdoc.synthetic_science import DEMO_POINT, METHODS, RECIPE, synthetic_scene

from workspace import build_workspace


def encode(data):
    return json.dumps(data, allow_nan=False, sort_keys=True, indent=2) + "\n"


def build(root: Path):
    package = Package(schema_version=1, package_id=RECIPE, version="1",
                      datasets=(), products=(), footprints=())
    engine = DocumentationEngine(package)
    rows = list(synthetic_scene(engine))
    dataset = {
        "schema_version": 1,
        "data_status": "synthetic",
        "recipe_id": RECIPE,
        "methods": METHODS,
        "grid": "HPX128 NESTED",
        "grid_cell_count": engine.grid.count,
        "boundary_step": engine.policy.boundary_step,
        "example_cell_id": engine.grid.cell_at(DEMO_POINT).id,
        "missing_cells": "Outside the synthetic fixture. No result available.",
        "cells": rows,
    }
    directory = root / "synthetic-science"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "synthetic-science-context.json"
    payload = encode(dataset).encode()
    temporary = output.with_suffix(".part")
    temporary.write_bytes(payload)
    temporary.replace(output)
    print(f"{len(rows)} synthetic cells of {engine.grid.count} · SHA-256 {sha256(payload).hexdigest()}")
    return output


if __name__ == "__main__":
    build(build_workspace())
