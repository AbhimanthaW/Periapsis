import pytest

from marsdoc import Package
from marsdoc.contracts import Dataset, Footprint, Global, Inventory, Polygon, Product
from marsdoc.grid import CANONICAL

URL = "https://example.org/synthetic"


def box(west, south, east, north):
    return Polygon(type="Polygon", coordinates=(((west, south), (east, south), (east, north),
                                                 (west, north), (west, south)),))


def dataset(modality="stereo_topography", product_class="stereo_dtm", **updates):
    values = dict(id=modality, mission="Synthetic", instrument="Fixture", modality=modality,
                  product_class=product_class, archive_url=URL, version="fixture-1",
                  catalogue_status="complete")
    return Dataset(**(values | updates))


def product(id="a", dataset_id="stereo_topography", **updates):
    values = dict(id=id, dataset_id=dataset_id, version="fixture-1", source_url=URL,
                  source_crs=CANONICAL, processing_level="derived", readiness="usable",
                  observation_extent_complete=True, support_extent_complete=True,
                  variables=("elevation",), native_spacing_m=2, effective_scale_m=6,
                  provenance=("synthetic fixture",))
    return Product(**(values | updates))


def footprint(prod="a", shape=None, **updates):
    values = dict(id=f"{prod}-support", product_id=prod, source_url=URL,
                  status="canonical_verified", coverage_kind="usable_support",
                  geometry=shape if shape is not None else Global(type="Global"),
                  transform="fixture canonical")
    return Footprint(**(values | updates))


def inventory(modality="stereo_topography", dataset_ids=None, **updates):
    values = dict(id=f"{modality}-scope", modality=modality,
                  dataset_ids=(modality,) if dataset_ids is None else dataset_ids,
                  status="complete", scope=Global(type="Global"), source_url=URL,
                  authority="fixture authority")
    return Inventory(**(values | updates))


def package(datasets=(), products=(), footprints=(), inventories=()):
    return Package(schema_version=1, package_id="synthetic", version="fixture-1",
                   datasets=datasets, products=products, footprints=footprints, inventories=inventories)


@pytest.fixture
def catalogue():
    return package((dataset(),), (product(),), (footprint(),), (inventory(),))
