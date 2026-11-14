"""Pinned release integrity and observed population checks."""

import pytest

from ranking.inputs import inspect, verify_digest


def test_changed_input_is_rejected(tmp_path):
    path = tmp_path / "asset.gz"
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="SHA-256 mismatch.*actual"):
        verify_digest(path, "0" * 64)


def test_pinned_release_counts():
    directory = __import__("pathlib").Path("data/ranking-inputs")
    if not directory.exists():
        pytest.skip("Release assets are not committed; supply them in data/ranking-inputs")
    result = inspect(directory)
    assert result["counts"] == {
        "catalogue_cells": 69178, "crism_cells": 1962, "distinct_unit_codes": 44,
        "dtm_cells": 114, "hirise_cells": 7425, "missing_albedo": 0,
        "missing_elevation": 0, "no_unit": 240, "ranking_rows": 196608,
        "rows": 196608, "sourced_rows": 196608, "sparse": 3304,
        "swim_covered": 170040, "thermal_archive_interpolated": 14577,
        "thermal_archive_noninterpolated": 181782,
        "targeted_product_cells": 8655, "thermal_no_positive_sample": 249,
        "two_units": 4,
    }
    assert result["groups"] == {
        "Apron Units": 2258, "Basin Units": 3325, "Highland Units": 86397,
        "Impact Unit": 10732, "Lowland Units": 25776,
        "Polar Units": 6403, "Transition Units": 18972,
        "Volcanic Units": 42505,
    }
    assert result["feature_counts"] == {
        "cave_candidates": 1062, "chlorides": 642, "dunes": 1462,
        "gazetteer": 2054, "hydrated_mineral_sites": 1851,
        "marsquakes": 189, "paleolakes": 425, "structures": 3588,
    }
