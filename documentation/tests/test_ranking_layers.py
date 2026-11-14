"""Regression tests for the sourced cell map joins."""
from collections import defaultdict
import gzip
import importlib
import json
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
import pytest


@pytest.fixture
def layers(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "cell-map"))
    return importlib.import_module("build_ranking_layers")


def test_point_validation_and_seam(layers):
    assert layers.point("same", -5, 14) == layers.point("same", 355, 14)
    with pytest.raises(ValueError):
        layers.point("bad", 0, 91)
    with pytest.raises(ValueError):
        layers.point("bad", float("nan"), 0)


def test_approximate_bounds_split_at_zero(layers):
    feature = layers.point("f", 359, 2, published_bounds=[357, 0, 3, 4])
    assert [part.bounds for part in layers.bounds_boxes(feature)] == [
        (357, 0, 360, 4), (0, 0, 3, 4),
    ]
    feature["published_bounds"] = [350, 20, 15, 24]
    assert layers.bounds_boxes(feature) == []


def test_named_bounds_keep_fraction_and_require_relevant_adopted_type(layers, monkeypatch):
    monkeypatch.setattr(layers, "GRID", layers.Grid(4))
    monkeypatch.setattr(layers, "SUBGRID", layers.Grid(32))
    a = layers.point("accepted", 359, 4, published_bounds=[348, -8, 9, 16],
                     type_code="FO", approval="Adopted by IAU")
    b = dict(a, id="unapproved", approval="Dropped")
    c = dict(a, id="unrelated", type_code="AA")
    cells = defaultdict(dict)
    assert layers.add_named_extents([a, b, c], cells) == 1
    assert cells
    for cell in cells.values():
        fractions = cell["gazetteer_approximate_bounds"]
        assert set(fractions) == {"accepted"}
        assert 0 < fractions["accepted"] < 1
        assert fractions["accepted"] * 64 == round(fractions["accepted"] * 64)


def test_projected_line_conserves_mars_sphere_length_across_cells(layers):
    native = CRS.from_proj4("+proj=robin +R=3396190 +units=m +type=crs")
    projection = Transformer.from_crs(native.geodetic_crs, native, always_xy=True)
    path = list(zip(*projection.transform([-1.0, 1.0], [0.0, 0.0]), strict=True))
    indices, lengths = layers.segment_bins(path, projection)
    expected = 2 * np.pi * layers.RADIUS_M / 180
    assert len(set(indices)) >= 2
    assert sum(lengths) == pytest.approx(expected, rel=1e-8)
    assert (lengths > 0).all()


def test_merge_requires_every_id_and_preserves_baseline(layers, monkeypatch, tmp_path):
    monkeypatch.setattr(layers, "GRID", layers.Grid(1))
    expansion = tmp_path / "expansion"
    expansion.mkdir()
    ranking = tmp_path / "ranking"
    ranking.mkdir()
    baseline = expansion / "cells-enriched.ndjson.gz"
    supplement = ranking / "cell-ranking.ndjson.gz"
    ids = [layers.GRID.identifier(i) for i in range(layers.GRID.count)]
    base_rows = [{"cell_id": identifier, "terrain": {"status": "Unclassified"}} for identifier in ids]
    baseline.write_bytes(gzip.compress(b"".join(map(layers.encode, base_rows))))
    manifest = {"sha256": layers.digest(baseline), "rows": len(ids)}
    (expansion / "enriched-manifest.json").write_text(json.dumps(manifest))
    rows = [{"cell_id": identifier, "evidence": {}} for identifier in ids]
    rows[0]["evidence"] = {"paleolakes": ["CBL-1"]}
    supplement.write_bytes(gzip.compress(b"".join(map(layers.encode, rows))))
    merged, _ = layers.merge_export(tmp_path, ranking)
    with gzip.open(merged, "rt") as stream:
        result = [json.loads(line) for line in stream]
    assert result[0]["sourced_catalogue_context"] == {"paleolakes": ["CBL-1"]}
    assert result[1]["sourced_catalogue_context"] == {}
    assert [row["terrain"] for row in result] == [row["terrain"] for row in base_rows]
    prior = layers.digest(merged)
    rows[-1]["cell_id"] = ids[0]
    supplement.write_bytes(gzip.compress(b"".join(map(layers.encode, rows))))
    with pytest.raises(ValueError, match="diverge"):
        layers.merge_export(tmp_path, ranking)
    assert layers.digest(merged) == prior


def test_source_digest_rejects_tampering(layers, tmp_path):
    snapshot = tmp_path / "source.csv"
    snapshot.write_bytes(b"old")
    receipt = {"bytes": 3, "sha256": layers.digest(snapshot)}
    layers.verify(snapshot, receipt)
    snapshot.write_bytes(b"new")
    with pytest.raises(ValueError, match="does not match lock"):
        layers.verify(snapshot, receipt)


def test_hydrated_points_preserve_products_and_deduplicate_exact_rows(layers, tmp_path):
    label = tmp_path / "hydrous_sites_geo_map.lbl"
    label.write_text("TARGET_NAME = MARS\nFILE_RECORDS = 3\ngiven by its planetocentric coordinates\n")
    (tmp_path / "hydrous_sites_geo_map.csv").write_text(
        "-5,14,,FRT001\n-5,14,,FRT001\n-5,14,ORB001,\n")
    a, b = layers.hydrated_mineral_points(tmp_path)
    assert a["crism_edr"] == "FRT001"
    assert b["omega_edr"] == "ORB001"
    assert a["lon_deg_east"] == b["lon_deg_east"] == 355
    assert "mineral_class" not in a
    label.write_text(label.read_text().replace("FILE_RECORDS = 3", "FILE_RECORDS = 4"))
    with pytest.raises(ValueError, match="row count"):
        list(layers.hydrated_mineral_points(tmp_path))
