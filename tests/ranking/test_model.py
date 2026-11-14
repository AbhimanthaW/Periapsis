"""Acceptance checks against the pinned cell-map export and compiled pack."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from pathlib import Path
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest

from ranking.build import build, compile_ranking, propagate
from ranking.engine import Engine, groups
from ranking.lexicon import Parser
from ranking.pack import Pack
from ranking.ledger import load
from ranking.service import RankRequest, RankingService


def test_parser_abstention_and_negation():
    parser = Parser()
    assert not parser.parse("purple unicorn")["concepts"]
    result = parser.parse("not volcanic ancient lake sediments")
    assert [item["id"] for item in result["negated"]] == ["volcanic"]
    assert {item["id"] for item in result["concepts"]} == {"age-noachian", "lake", "sedimentary"}
    assert not parser.parse("deltas")["concepts"]
    assert parser.parse("deltas")["demo"][0]["included"] is False
    spans = parser.parse("not láva-flows ancient lakes")
    assert spans["negated"][0]["span"] == [4, 14]
    assert spans["concepts"][0]["span"] == [15, 22]


def test_synthetic_release_refused(tmp_path):
    with pytest.raises(ValueError, match="release pack cannot contain synthetic"):
        build(tmp_path, tmp_path / "pack", with_demo=True, release=True)


def load_service(name):
    path = Path("data") / name
    if not path.exists():
        pytest.skip(f"Build {path} for integration checks")
    return RankingService(path)


@pytest.fixture(scope="module")
def service():
    return load_service("ranking-pack")


@pytest.fixture(scope="module")
def demo_service():
    return load_service("ranking-demo")


def test_known_lake_and_coverage(service, demo_service):
    detail = service.detail("HPX128:24")
    assert detail["record"]["sourced_catalogue_context"]["paleolakes"] == ["OBL-185"]
    assert detail["concepts"]["lake"]["state"] == "Present"
    assert service.detail("HPX128:196607")["record"]["cell_id"] == "HPX128:196607"
    engine = service.engine
    lake = engine.ids["lake"]
    coverage = np.unpackbits(engine.pack["covered"][lake], count=196608)
    assert int(coverage.sum()) == 423
    assert detail["concepts"]["lake"]["support"] == 1.0
    for pack, matrix, bits in ((engine.pack, "support", "covered"),
                               (demo_service.engine.pack, "support_demo", "covered_demo")):
        coverage = np.unpackbits(pack[bits], axis=1, count=196608).astype(bool)
        assert not np.any((pack[matrix] > 0) & ~coverage)
        assert "cells.sqlite" in pack.manifest["files"]
        assert isinstance(pack[matrix], np.memmap)
        assert sum(path.stat().st_size for path in pack.directory.iterdir()) < 20_000_000

    assert not engine.pack.manifest["synthetic_layers"]
    expected = {
        "age-noachian": 92493, "age-hesperian": 90034, "age-amazonian": 52102,
        "highland": 86397, "massif": 5151, "lowland": 25776, "transition": 18972,
        "outflow": 1753, "basin": 3325, "impact": 10732, "volcanic": 42505,
        "volcanic-edifice": 1923, "volcanic-field": 1024, "young-volcanic": 9008,
        "polar-deposits": 6403, "polar-cap": 940, "polar-dunes": 410,
        "ice": 53339, "ice-shallow": 33856, "ice-deep": 48445, "rocky-surface": 3020,
        "dust-mantled": 32516, "dark-coarse-surface": 40803, "low-elevation": 27727,
        "high-elevation": 8326, "glacial-apron": 901, "mass-wasting": 1357,
    }
    assert {cid: engine.pack.manifest["record_concept_counts"][cid] for cid in expected} == expected
    augmented = {"outflow": 2265, "impact": 14205, "volcanic": 42559}
    for cid, count in (expected | augmented).items():
        assert engine.pack.manifest["n"][engine.ids[cid]] == count


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


def test_query_and_demo_quarantine(service, demo_service):
    request = RankRequest(schema_version=1, request_id="test", objective="ancient water and delta deposits", limit=3)
    demo_request = request.model_copy(update={"include_demo": True})
    demo = demo_service.rank(demo_request)
    ordinary = demo_service.rank(request)
    cold = RankingService(demo_service.engine.pack.directory).rank(request)
    assert ordinary == cold
    assert ordinary["areas"] == service.rank(request)["areas"]
    assert service.rank(demo_request)["areas"] == ordinary["areas"]
    assert ordinary["parse"]["demo"][0]["included"] is False
    assert all(not area["demo"] for area in ordinary["areas"])
    assert demo["parse"]["demo"][0]["included"] is True
    assert all(area["demo"] for area in demo["areas"])
    assert all(area["tier"] == "Direct" for area in demo["areas"])
    assert service.rank(RankRequest(schema_version=1, request_id="x", objective="purple unicorn"))["abstain"]
    for cell, cid in (("HPX128:96506", "delta"), ("HPX128:193729", "delta"),
                      ("HPX128:53326", "clays")):
        index = int(cell.split(":")[1])
        assert demo_service.engine.pack["support_demo"][service.engine.ids[cid], index] >= 128
        assert service.engine.pack["support"][service.engine.ids[cid], index] == 0


def test_filters_and_response_stability(service):
    engine = service.engine
    order = engine.pack.manifest["filter_order"]
    for name, expected in (("polar", 26653), ("volcanic", 42505)):
        mask = np.unpackbits(engine.pack["filters"][order.index(name)], count=196608)
        assert int(mask.sum()) == expected
    request = RankRequest(schema_version=1, request_id="stable", objective="ancient lakes", limit=3)
    assert service.rank(request) == service.rank(request)
    assert len(base64.b64decode(service.rank(request)["heat_nside32"])) == 12288


def test_broader_is_not_direct(demo_service):
    # Query a real hydrated-mineral site with no synthetic clay coverage.
    engine = demo_service.engine
    index = next(i for i in np.flatnonzero(engine.pack["support"][engine.ids["hydrated-minerals"]])
                 if not engine.pack["support_demo"][engine.ids["clays"], i])
    request = RankRequest(schema_version=1, request_id="broader", objective="clays", include_demo=True, limit=3)
    response = demo_service.rank(request)
    assert response["counts"]["thematic_cells"] > 0
    assert response["areas"]
    assert engine.pack["support_demo"][engine.ids["clays"], index] == 0
    # Only the parent is covered. This cell can contribute thematic affinity,
    # but must never appear in the Direct areas.
    assert all(f"HPX128:{index}" not in area["cells"] for area in response["areas"])


def test_real_arcadia_ice_and_cerberus_graben(service):
    engine = service.engine
    from marsdoc.grid import Grid
    lon, lat = Grid(128).centroids(np.arange(196608)).T
    arcadia = (lon >= 165.8) & (lon <= 210.4) & (lat >= 33.9) & (lat <= 64.2)
    assert np.any(arcadia & (engine.pack["support"][engine.ids["ice-shallow"]] >= 128))
    assert any(
        engine.pack["support"][engine.ids["graben"], index] >= 128
        and any(engine.features["structures"][fid]["interpretation"] == "Graben axis"
                for fid in evidence.get("structures", {}))
        for index, evidence in engine.catalogue.items()
        if 157 <= lon[index] <= 174 and 6 <= lat[index] <= 12
    )


def test_cache_isolates_parse_and_limit(service):
    request = RankRequest(schema_version=1, request_id="cache", objective="water", limit=2, exclude=["polar", "volcanic"])
    second = request.model_copy(update={"request_id": "second", "objective": "water not hydrothermal",
                                        "exclude": ["volcanic", "polar", "polar"], "limit": 7})
    first_result = service.rank(request)
    second_result = service.rank(second)
    assert first_result["areas"] == second_result["areas"][:2]
    assert second_result["areas"] == RankingService(service.engine.pack.directory).rank(second)["areas"]
    assert first_result["counts"] == second_result["counts"]
    assert first_result["parse"] != second_result["parse"]
    assert second_result["request_id"] == "second"
    assert len(second_result["areas"]) == 7
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(result == second_result for result in pool.map(service.rank, [second] * 32))


def test_ice_is_not_inferred_from_aprons_or_other_depths():
    concepts = load()
    ids = {item["id"]: i for i, item in enumerate(concepts)}
    support = np.zeros((len(concepts), 3), dtype=np.uint8)
    covered = np.zeros(support.shape, dtype=bool)
    support[ids["glacial-apron"], :2] = 255
    covered[ids["glacial-apron"], :2] = True
    covered[ids["ice"], 1] = True
    support[ids["ice"], 2] = 255
    covered[ids["ice"], 2] = True
    propagate(concepts, support, covered)
    assert support[ids["ice"]].tolist() == [0, 0, 255]
    assert covered[ids["ice"]].tolist() == [False, True, True]
    assert not np.any(support[ids["ice-shallow"]])


def test_pack_rejects_missing_or_changed_detail_store(service, tmp_path):
    original = service.engine.pack.directory
    for path in original.iterdir():
        if path.name != "cells.sqlite":
            shutil.copy2(path, tmp_path / path.name)
    with pytest.raises(FileNotFoundError):
        Pack(tmp_path)
    (tmp_path / "cells.sqlite").write_text("different detail store")
    with pytest.raises(ValueError, match="cells.sqlite failed SHA-256"):
        Pack(tmp_path)
    shutil.copy2(original / "cells.sqlite", tmp_path / "cells.sqlite")
    (tmp_path / "catalogue-context.json.gz").write_text("different catalogue")
    with pytest.raises(ValueError, match="catalogue-context.json.gz failed SHA-256"):
        Pack(tmp_path)


def test_layer_cache_isolates_structure_threshold():
    inputs = Path("data/ranking-inputs")
    baseline, baseline_meta = compile_ranking(inputs, False)
    changed, changed_meta = compile_ranking(inputs, False, structure_max=8)
    first = baseline_meta["layer_cache_keys"]
    second = changed_meta["layer_cache_keys"]
    assert first["base"] == second["base"]
    assert first["catalogue"] != second["catalogue"]
    assert (inputs.parent / "ranking-layer-cache" / f"base-{first['base']}.npz").exists()
    assert (inputs.parent / "ranking-layer-cache" / f"catalogue-{second['catalogue']}.npz").exists()
    ice = baseline_meta["concept_order"].index("ice")
    graben = baseline_meta["concept_order"].index("graben")
    assert np.array_equal(baseline["support"][ice], changed["support"][ice])
    assert np.any(baseline["support"][graben] != changed["support"][graben])


@pytest.mark.parametrize("with_demo", [False, True], ids=["release", "demo"])
def test_rebuild_determinism(tmp_path, with_demo):
    inputs = Path("data/ranking-inputs")
    if not inputs.exists():
        pytest.skip("Pinned release assets are required")
    first, second = tmp_path / "first", tmp_path / "second"
    build(inputs, first, with_demo=with_demo, release=not with_demo)
    build(inputs, second, with_demo=with_demo, release=not with_demo)
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert Pack(first).manifest["files"] == Pack(second).manifest["files"]


@pytest.mark.parametrize("density", [0.01, 0.15, 0.50, 0.85, 1.0])
def test_vector_components_match_reference(service, density):
    neighbours = service.engine.pack["neighbours"]
    selected = np.random.default_rng(18).random(196608) < density
    actual = {frozenset(map(int, group)) for group in groups(selected, neighbours)}
    remaining = set(map(int, np.flatnonzero(selected)))
    expected = set()
    while remaining:
        start = remaining.pop()
        component = {start}
        pending = [start]
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
        for schema_version in (True, 1.0):
            invalid = json.dumps({"schema_version": schema_version, "request_id": "http", "objective": "lake"}).encode()
            invalid_request = urllib.request.Request(root + "/api/v1/rank", invalid, {"Content-Type": "application/json"})
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(invalid_request)
            assert error.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(root + "/api/v1/cell/HPX128:999999")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_top_golden_area_order(demo_service):
    from tests.ranking.check_sensitivity import top_areas

    expected = json.loads(Path(__file__).with_name("golden_areas.json").read_text())
    actual = top_areas(demo_service.engine)
    assert all(len(matches) == 20 for matches in actual.values())
    assert {objective: [[tile, cells[0]] for tile, cells in matches]
            for objective, matches in actual.items()} == expected
