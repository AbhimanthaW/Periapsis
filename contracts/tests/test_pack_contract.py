import json
from pathlib import Path
import shutil

from jsonschema import Draft202012Validator
from marsdoc import CapabilityQuery
import numpy as np
import pytest
from pyproj import CRS, Transformer

from contracts.fixtures.generate import build
from contracts.pack import PackError, center, check_pack, pin

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/synthetic-v1"
CAP = "routing_simulation"


@pytest.fixture
def copy_pack(tmp_path):
    return shutil.copytree(FIXTURE, tmp_path / "pack")


def edit_site(path, change):
    site = json.loads((path / "site.json").read_bytes())
    change(site)
    (path / "site.json").write_text(json.dumps(site))


def repin(path, role, file):
    edit_site(path, lambda site: site["artifacts"].update({role: pin(file.name, file.read_bytes())}))


def fails(path, code, capability=CAP):
    with pytest.raises(PackError) as error:
        check_pack(path, capability=capability)
    assert error.value.code == code


@pytest.mark.parametrize("name", sorted(ROOT.glob("*.schema.json")))
def test_schemas(name):
    Draft202012Validator.check_schema(json.loads(name.read_bytes()))


def test_regeneration(tmp_path):
    regenerated = tmp_path / "new"
    build(regenerated)
    assert {p.name: p.read_bytes() for p in regenerated.iterdir()} == {
        p.name: p.read_bytes() for p in FIXTURE.iterdir()
    }


def test_independent_controls():
    pack = check_pack(FIXTURE, capability=CAP)
    assert pack.elevations.shape == (3, 5)
    assert pack.elevations.dtype == np.dtype("<f4")
    assert not pack.elevations.flags.writeable
    assert pack.elevations[1, 0] == 0
    assert pack.terrain["valid_mask"].sum() == 14
    assert np.argwhere(~pack.terrain["valid_mask"]).tolist() == [[2, 3]]
    assert np.argwhere(pack.terrain["screen_excluded_mask"]).tolist() == [[2, 1]]
    for cell, xy in [((0, 0), (105, 195)), ((1, 4), (145, 185)), ((2, 3), (135, 175)), ((2, 4), (145, 175))]:
        assert center(pack.site["grid"], *cell) == xy
    crs = CRS.from_wkt(pack.site["reference"]["local_crs_wkt"])
    inverse = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
    for xy, eligible in [((105, 185), True), ((135, 175), False)]:
        query = CapabilityQuery.model_validate(dict(schema_version=1,
            geometry=dict(type="Point", coordinates=inverse.transform(*xy)),
            requested=dict(id="elevation", requirements=[dict(variable="elevation",
                           product_classes=["stereo_dtm"], max_native_spacing_m=10)])))
        assert pack.evidence.resolve(query).requested.eligible is eligible
    fails(FIXTURE, "CAPABILITY_UNAVAILABLE", "tactical_routing")


@pytest.mark.parametrize("version", [2, True, "1", 1.0])
def test_refuse_versions(copy_pack, version):
    edit_site(copy_pack, lambda site: site.update(schema_version=version))
    (copy_pack / "terrain.npz").unlink()
    fails(copy_pack, "UNSUPPORTED_SCHEMA")


@pytest.mark.parametrize("name,code", [("terrain.npz", "MISSING_ARTIFACT"), ("evidence.json", "MISSING_EVIDENCE")])
def test_missing(copy_pack, name, code):
    (copy_pack / name).unlink()
    fails(copy_pack, code)


def test_corruption(copy_pack):
    path = copy_pack / "terrain.npz"
    raw = bytearray(path.read_bytes())
    raw[0] ^= 1
    path.write_bytes(raw)
    fails(copy_pack, "CHECKSUM_MISMATCH")


@pytest.mark.parametrize("index,value", [(0, 0), (1, 1), (4, 10), (5, 123)])
def test_bad_grid(copy_pack, index, value):
    edit_site(copy_pack, lambda site: site["grid"]["affine"].__setitem__(index, value))
    fails(copy_pack, "INVALID_GRID")


@pytest.mark.parametrize("value", [10**30, 10**400])
def test_oversized_grid_coordinate(copy_pack, value):
    edit_site(copy_pack, lambda site: site["grid"]["affine"].__setitem__(2, value))
    fails(copy_pack, "INVALID_GRID")


@pytest.mark.parametrize("key,mutate,code", [
    ("z_m", lambda a: a.T, "INVALID_TERRAIN"),
    ("z_m", lambda a: a.astype(object), "INVALID_TERRAIN"),
    ("valid_mask", lambda a: a[None], "INVALID_TERRAIN"),
    ("valid_mask", np.logical_not, "INVALID_MASK"),
    ("screen_excluded_mask", np.logical_not, "INVALID_MASK"),
    ("screen_excluded_mask", lambda a: a.astype("u1"), "INVALID_MASK"),
])
def test_bad_arrays(copy_pack, key, mutate, code):
    path = copy_pack / "terrain.npz"
    with np.load(path, allow_pickle=False) as original:
        arrays = dict(original)
    arrays[key] = mutate(arrays[key])
    np.savez(path, **arrays)
    repin(copy_pack, "terrain", path)
    fails(copy_pack, code)


def test_unlinked_evidence(copy_pack):
    path = copy_pack / "evidence.json"
    evidence = json.loads(path.read_bytes())
    evidence["products"][0]["version"] = "unrelated"
    path.write_text(json.dumps(evidence))
    repin(copy_pack, "evidence", path)
    fails(copy_pack, "EVIDENCE_UNSUPPORTED")


def test_untrusted_path(copy_pack):
    path = copy_pack / "terrain.npz"
    path.rename(copy_pack.parent / path.name)
    path.symlink_to(copy_pack.parent / path.name)
    fails(copy_pack, "INVALID_ARTIFACT")


def test_artifact_traversal_rejected(copy_pack):
    edit_site(copy_pack, lambda site: site["artifacts"]["terrain"].update(path="../terrain.npz"))
    fails(copy_pack, "INVALID_SCHEMA")


def test_integral_artifact_size(copy_pack):
    edit_site(copy_pack, lambda site: site["artifacts"]["terrain"].update(size_bytes=814.0))
    assert check_pack(copy_pack, capability=CAP).elevations.shape == (3, 5)


@pytest.mark.parametrize("state", ["pass_fixture", "not_applicable", "unsupported"])
def test_g10_requires_external_acceptance(copy_pack, state):
    edit_site(copy_pack, lambda site: site["gates"]["G10"].update(state=state))
    fails(copy_pack, "INVALID_SCHEMA")
