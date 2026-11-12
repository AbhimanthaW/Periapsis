from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from contracts.pack import PackError
from runtime.mission import load_pack, simulate

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "contracts/fixtures/synthetic-v1"


def test_fixture_requires_opt_in():
    with pytest.raises(PackError, match="CAPABILITY_UNAVAILABLE"):
        load_pack(FIXTURE)
    with pytest.raises(PackError, match="CHECKSUM_MISMATCH"):
        load_pack(FIXTURE, simulation=True, site_sha256="0" * 64)


def test_closure_and_reserve():
    pack = load_pack(FIXTURE, simulation=True, site_sha256=sha256((FIXTURE / "site.json").read_bytes()).hexdigest())
    initial = simulate(pack)
    assert initial["direct_return"]["seconds"] == 40
    assert initial["reverse_control"]["seconds"] == 48
    assert initial["return_margin_s"] == 45
    assert initial["recommendation"] == "science-a"
    assert initial["science"] == [{"id": "science-a", "seconds": 75, "margin_s": 10, "feasible": True}]
    assert initial["completed_task_ids"] == ["survey-done"]
    closed = simulate(pack, closures=["mid"])
    assert closed["direct_return"]["seconds"] == 60
    assert (1, 2) not in closed["direct_return"]["cells"]
    assert closed["return_margin_s"] == 25
    assert closed["recommendation"] == "direct_return"
    assert closed["science"] == [{"id": "science-a", "seconds": 95, "margin_s": -10, "feasible": False}]
    assert simulate(pack, closures=["mid"]) == closed
    assert simulate(pack) == initial
    insufficient = simulate(pack, closures=["mid"], remaining_s=70)
    assert insufficient["status"] == "RETURN_OVER_RESERVE"
    assert insufficient["return_margin_s"] == -5
    assert insufficient["science"] == []
    assert insufficient["recommendation"] is None
    blocked = simulate(pack, closures=["mid", "north"])
    assert blocked["status"] == "NO_RETURN_ROUTE"
    assert blocked["direct_return"] is None
    assert blocked["science"] == []
    assert blocked["recommendation"] is None


def test_cli_replay():
    result = subprocess.run([sys.executable, "-m", "runtime.mission", "simulate", str(FIXTURE), "--closure", "mid"],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)["direct_return"]["seconds"] == 60
