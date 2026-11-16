import json

import pytest

from runtime import release


def test_release_requires_matching_bundle_and_checkout(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    contract = source / "contract.json"
    contract.write_text("{}")
    monkeypatch.setattr(release, "ROOT", source)

    bundle = tmp_path / "bundle"
    for name in ("app", "legacy", "ranking"):
        (bundle / name).mkdir(parents=True)
    (bundle / "app/index.html").write_text("<html>Mission</html>")
    (bundle / "legacy/index.html").write_text("<html>Atlas</html>")
    (bundle / "ranking/manifest.json").write_text("{}")
    forecast = bundle / "forecast.json"
    forecast.write_text('{"model_id": "fixture"}')
    manifest = {
        "schema_version": 2,
        "revision": "test-revision",
        "ranking_pack_sha256": release.digest(bundle / "ranking/manifest.json"),
        "forecast_model_id": "fixture",
        "source_files": {"contract.json": release.digest(contract)},
        "files": release.index(bundle),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert release.verify(bundle) == manifest

    contract.write_text('{"version": 2}')
    with pytest.raises(ValueError, match="Release source mismatch"):
        release.verify(bundle)
    contract.write_text("{}")

    forecast.write_text('{"model_id": "other"}')
    with pytest.raises(ValueError, match="Packaged files differ"):
        release.verify(bundle)
