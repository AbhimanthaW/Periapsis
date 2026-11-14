"""Reviewed concept inventory. Rules are the supplied implementation prompt, v2."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name("concepts.json")
STATUSES = {"live", "live-flagged", "catalogue", "demo", "unsupported"}


def load(path: Path = PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != "cell-concepts-v2":
        raise ValueError("unexpected concept ledger version")
    concepts = data["concepts"]
    ids = [item["id"] for item in concepts]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate concept ID")
    for item in concepts:
        if item["status"] not in STATUSES or not set(item["broader"]) <= set(ids):
            raise ValueError(f"invalid concept {item['id']}")
        if item["id"] in item["broader"]:
            raise ValueError(f"self-parent concept {item['id']}")
    return concepts
