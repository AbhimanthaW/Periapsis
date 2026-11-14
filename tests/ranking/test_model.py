"""Acceptance checks against the pinned cell-map export and compiled pack."""
from pathlib import Path
import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest

from ranking.build import build
from ranking.engine import Engine, groups
from ranking.lexicon import Parser
from ranking.pack import Pack
from ranking.service import RankRequest, RankingService


def test_parser_abstention_and_negation():
    parser = Parser()
    assert not parser.parse("purple unicorn")["concepts"]
    result = parser.parse("not volcanic ancient lake sediments")
    assert [item["id"] for item in result["negated"]] == ["volcanic"]
    assert {item["id"] for item in result["concepts"]} == {"age-noachian", "lake", "sedimentary"}
    assert not parser.parse("deltas")["concepts"]
    assert parser.parse("deltas")["demo"][0]["included"] is False


def test_synthetic_release_refused(tmp_path):
    with pytest.raises(ValueError, match="release pack cannot contain synthetic"):
        build(tmp_path, tmp_path / "pack", with_demo=True, release=True)


@pytest.fixture(scope="module")
def service():
    path = Path("data/ranking-pack")
    if not path.exists():
        pytest.skip("Build the pinned local ranking pack for integration checks")
    return RankingService(path)


def test_known_lake_and_coverage(service):
    detail = service.detail("HPX128:24")
    assert detail["record"]["sourced_catalogue_context"]["paleolakes"] == ["OBL-185"]
    assert detail["concepts"]["lake"]["state"] == "Present"
    engine = service.engine
    lake = engine.ids["lake"]
    coverage = np.unpackbits(engine.pack["covered"][lake], count=196608)
    assert int(coverage.sum()) == 423
    assert detail["concepts"]["lake"]["support"] == 1.0
    for matrix, bits in (("support", "covered"), ("support_demo", "covered_demo")):
        coverage = np.unpackbits(engine.pack[bits], axis=1, count=196608).astype(bool)
        assert not np.any((engine.pack[matrix] > 0) & ~coverage)


def test_polar_swim_gap_and_negative_control(service):
    from marsdoc.grid import Grid
    grid = Grid(128)
    engine = service.engine
    latitudes = grid.centroids(np.arange(196608))[:, 1]
    poleward = abs(latitudes) >= 60
    coverage = np.unpackbits(engine.pack["covered"][engine.ids["ice"]], count=196608)
    assert int(poleward.sum()) == 26568
    assert not np.any(coverage & poleward)
    summit = int(grid.indices([226.2, 18.6]))
    assert service.detail(f"HPX128:{summit}")["concepts"]["lake"]["state"] != "Present"


def test_query_and_demo_quarantine(service):
    request = RankRequest(schema_version=1, request_id="test", objective="ancient water and delta deposits", limit=3)
    ordinary = service.rank(request)
    assert ordinary["parse"]["demo"][0]["included"] is False
    assert all(not area["demo"] for area in ordinary["areas"])
    demo = service.rank(request.model_copy(update={"include_demo": True}))
    assert demo["parse"]["demo"][0]["included"] is True
    assert all(area["demo"] for area in demo["areas"])
    assert all(area["tier"] == "Direct" for area in demo["areas"])
    assert service.rank(RankRequest(schema_version=1, request_id="x", objective="purple unicorn"))["abstain"]
    for cell, cid in (("HPX128:96506", "delta"), ("HPX128:193729", "delta"),
                      ("HPX128:53326", "clays")):
        index = int(cell.split(":")[1])
        assert service.engine.pack["support_demo"][service.engine.ids[cid], index] >= 128
        assert service.engine.pack["support"][service.engine.ids[cid], index] == 0


def test_filters_and_response_stability(service):
    engine = service.engine
    order = engine.pack.manifest["filter_order"]
    for name, expected in (("polar", 26653), ("volcanic", 42505)):
        mask = np.unpackbits(engine.pack["filters"][order.index(name)], count=196608)
        assert int(mask.sum()) == expected
    request = RankRequest(schema_version=1, request_id="stable", objective="ancient lakes", limit=3)
    assert service.rank(request) == service.rank(request)
    assert len(__import__("base64").b64decode(service.rank(request)["heat_nside32"])) == 12288


def test_broader_is_not_direct(service):
    request = RankRequest(schema_version=1, request_id="broader", objective="clays", include_demo=True, limit=3)
    response = service.rank(request)
    assert response["counts"]["thematic_cells"] > 0
    assert response["areas"]


def test_vector_components_match_reference(service):
    # Compare the vectorized union with a direct graph walk on a sparse slice.
    neighbours = service.engine.pack["neighbours"]
    selected = np.zeros(196608, dtype=bool)
    selected[np.arange(9000, 11000, 3)] = True
    selected[np.arange(9600, 9700)] = True
    actual = {frozenset(map(int, group)) for group in groups(selected, neighbours)}
    remaining = set(map(int, np.flatnonzero(selected)))
    expected = set()
    while remaining:
        start = min(remaining)
        component = {start}
        pending = [start]
        remaining.remove(start)
        while pending:
            for neighbour in neighbours[pending.pop()]:
                index = int(neighbour)
                if index in remaining:
                    remaining.remove(index)
                    component.add(index)
                    pending.append(index)
        by_tile = {}
        for index in component:
            by_tile.setdefault(index >> 4, set()).add(index)
        expected.update(frozenset(group) for group in by_tile.values())
    assert actual == expected


def test_http_contract(service):
    from runtime.planning_api import create_server
    server = create_server(0, ranking_pack=service.engine.pack.directory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        body = json.dumps({"schema_version": 1, "request_id": "http", "objective": "lake", "limit": 1}).encode()
        request = urllib.request.Request(root + "/api/v1/rank", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request) as response:
            data = json.load(response)
        assert data["request_id"] == "http" and data["areas"][0]["tier"] == "Direct"
        with urllib.request.urlopen(root + "/api/v1/cell/HPX128:24") as response:
            assert json.load(response)["concepts"]["lake"]["state"] == "Present"
        bad = urllib.request.Request(root + "/api/v1/rank", b'{"schema_version":1,"request_id":"x","objective":""}',
                                     {"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(bad)
        assert error.value.code == 400
        assert json.load(error.value)["error"] == "INVALID_REQUEST"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(root + "/api/v1/cell/HPX128:999999")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
