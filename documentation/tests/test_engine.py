import math

import pytest
from shapely import union_all

from marsdoc import CapabilityQuery, DocumentationEngine
from marsdoc.contracts import Bounds, ModalityPolicy, Polygon, ScoringPolicy
from marsdoc.engine import _tier, default_policy
from marsdoc.spatial import Window
from conftest import box, dataset, footprint, inventory, package, product


def stereo(result):
    return next(metric for metric in result.modalities if metric.modality == "stereo_topography")


def cell(engine, lon=0, lat=1):
    return engine.summarize(engine.grid.cell_at((lon, lat)).id)


def query(geometry=None, *, variable="elevation", classes=("stereo_dtm",), spacing=2,
          width=None, fallback=False, **extra):
    return CapabilityQuery.model_validate({
        "schema_version": 1,
        "geometry": geometry or {"type": "Point", "coordinates": [0, 0]},
        "corridor_width_m": width,
        "requested": {"id": "primary", "requirements": [{
            "variable": variable, "product_classes": classes, "max_native_spacing_m": spacing, **extra,
        }]},
        "fallbacks": [{"id": "fallback", "requirements": [{
            "variable": variable, "product_classes": classes, "max_native_spacing_m": 20,
        }]}] if fallback else [],
    })


def test_partial_overlapping_duplicates_and_determinism():
    a, b = product(), product("b")
    first, second = footprint(shape=box(-.08, .98, .08, 1.04)), footprint("b", box(0, .98, .10, 1.04))
    # Same narrow swath duplicated under another footprint ID and in the input arrays.
    dup = first.model_copy(update={"id": "duplicate-geometry"})
    inv = inventory()
    one = DocumentationEngine(package((dataset(),), (a,), (first,), (inv,)))
    two = DocumentationEngine(package((dataset(),), (b, a, a), (second, dup, first, first), (inv,)))
    reversed_order = DocumentationEngine(package((dataset(),), (a, b), (first, second, dup), (inv,)))
    summary = cell(two)
    metric = stereo(summary)
    assert 0 < stereo(cell(one)).observed_fraction < metric.observed_fraction < .2
    assert metric.observed_fraction == pytest.approx(metric.evidence_score, abs=1e-13)
    assert metric.product_ids == ("a", "b")
    assert summary.model_dump_json() == cell(reversed_order).model_dump_json()
    assert summary.provenance[0].product.provenance == ("synthetic fixture",)
    assert len(summary.provenance[0].footprints) == 2

    # Compare against the union of overlapping swaths in an independently wider window.
    big = Window.from_geometry(box(-1, .6, 1, 1.5))
    clips = [match.observed for match in two.catalogue.match(big)]
    assert big.fraction(union_all(clips)) < sum(big.fraction(item) for item in clips)


def test_partial_pixel_known_absent_and_missing_inventory():
    data = package((dataset(),), (), (), (inventory(scope=box(-1, -.1, 1, 2)),))
    engine = DocumentationEngine(data)
    assert stereo(cell(engine)).coverage_state == "verified_absence"
    unknown = stereo(cell(engine, 5, 1))
    assert unknown.coverage_state == "unknown"
    assert unknown.evidence_bounds == Bounds(lower=0, upper=1)
    # A scoped catalogue crossing the cell narrows the upper bound without closing it.
    partial = DocumentationEngine(package((dataset(),), (), (), (inventory(scope=box(-1, -.1, 0, 2)),)))
    metric = stereo(cell(partial))
    assert 0 < metric.observed_bounds.upper < 1
    assert metric.coverage_state == "unknown"


def test_incomplete_dataset_cannot_close_even_with_complete_inventory():
    engine = DocumentationEngine(package((dataset(catalogue_status="unknown"),), (), (), (inventory(),)))
    metric = stereo(cell(engine))
    assert metric.observed_bounds.upper == 1
    assert [issue.code for issue in metric.issues] == ["inventory_not_closed"]


@pytest.mark.parametrize("variant,code", [
    ("invalid", "footprint_rejected"),
    ("unavailable", "footprint_unavailable"),
    ("untransformable", "footprint_untransformable"),
    ("missing_crs", "missing_source_crs"),
    ("missing_footprint", "footprint_missing"),
])
def test_quarantined_support_does_not_establish_absence(variant, code):
    bow = Polygon(type="Polygon", coordinates=(((-1, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)),))
    prod = product(source_crs=None) if variant == "missing_crs" else product()
    fps = {
        "invalid": (footprint(shape=bow),),
        "unavailable": (footprint(status="unavailable", geometry=None),),
        "untransformable": (footprint(status="untransformable"),),
        "missing_crs": (footprint(),),
        "missing_footprint": (),
    }[variant]
    engine = DocumentationEngine(package((dataset(),), (prod,), fps, (inventory(),)))
    metric = stereo(cell(engine))
    assert metric.coverage_state == "unknown"
    assert metric.evidence_bounds == Bounds(lower=0, upper=1)
    assert code in {issue.code for issue in metric.issues}
    assert not engine.resolve(query()).requested.eligible


def test_observation_only_and_product_readiness():
    obs = footprint(coverage_kind="observation")
    engine = DocumentationEngine(package((dataset(),), (product(support_extent_complete=False),),
                                         (obs,), (inventory(),)))
    metric = stereo(cell(engine))
    assert metric.observed_fraction == 1 and metric.usable_fraction == 0
    assert metric.evidence_bounds == Bounds(lower=0, upper=1)
    assert not engine.resolve(query()).requested.eligible
    for readiness in ("unusable", "needs_preprocessing", "unknown"):
        engine = DocumentationEngine(package((dataset(),), (product(readiness=readiness),),
                                             (footprint(),), (inventory(),)))
        metric = stereo(cell(engine))
        assert metric.coverage_state == "verified_coverage"
        assert metric.evidence_bounds == Bounds(lower=0, upper=1 if readiness == "unknown" else 0)
        assert not engine.resolve(query()).requested.eligible


def test_reject_conflicting_duplicates(catalogue):
    dup = product(native_spacing_m=30)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        DocumentationEngine(catalogue.model_copy(update={"products": (*catalogue.products, dup)}))


def test_tiers_weights_and_numeric_bounds(catalogue):
    policy = default_policy()
    assert _tier(20 - 2e-9, policy) == "Very Low"
    assert _tier(20 - .5e-9, policy) == "Low"
    assert _tier(20, policy) == "Low"
    assert _tier(100, policy) == "Very High"
    first = cell(DocumentationEngine(catalogue)).terrain
    assert first.score is None and first.tier == "Unclassified"
    assert first.bounds.lower == 25 and first.bounds.upper == 100
    policies = [item.model_dump() for item in policy.modalities]
    for item in policies:
        if item["modality"] == "stereo_topography":
            item["weight"] = 20
    custom = ScoringPolicy.model_validate(policy.model_dump() | {"version": "sensitivity-test",
                                                                "modalities": policies})
    second = cell(DocumentationEngine(catalogue, policy=custom)).terrain
    assert second.tier == "Very High" and second.score is None
    assert second.bounds.lower == pytest.approx(2000 / 23)


def test_configured_utility_uses_spatial_max_and_preserves_coverage():
    policy = default_policy()
    policies = [item if item.modality != "stereo_topography" else ModalityPolicy(
        modality=item.modality, axis=item.axis, weight=1, good_spacing_m=1, poor_spacing_m=100)
        for item in policy.modalities]
    policy = ScoringPolicy.model_validate(policy.model_dump() | {"modalities": policies, "version": "ramp"})
    fine = footprint("fine", box(-.05, .98, .05, 1.02))
    inv = inventory()
    data = package((dataset(),), (product(native_spacing_m=10), product("fine", native_spacing_m=1)),
                   (footprint(), fine), (inv,))
    e = DocumentationEngine(data, policy=policy)
    fine_alone = DocumentationEngine(package((dataset(),), (product("fine", native_spacing_m=1),),
                                             (fine,), (inv,)), policy=policy)
    fine_fraction = stereo(cell(fine_alone)).usable_fraction
    result = stereo(cell(e))
    assert result.observed_fraction == 1 and result.usable_fraction == 1
    assert result.evidence_score == pytest.approx(.5 + .5 * fine_fraction)
    missing = DocumentationEngine(package((dataset(),), (product(native_spacing_m=None),),
                                          (footprint(),), (inv,)), policy=policy)
    assert stereo(cell(missing)).evidence_bounds == Bounds(lower=0, upper=1)


def test_hirise_image_cannot_supply_dtm_even_at_high_terrain_score():
    mods = ("baseline_topography", "context_imagery", "fine_imagery")
    sources = tuple(dataset(mod, "optical_image" if "imagery" in mod else "gridded_topography") for mod in mods)
    products = tuple(product(mod, mod, variables=("reflectance",) if "imagery" in mod else ("elevation",))
                     for mod in mods)
    e = DocumentationEngine(package(sources, products, tuple(footprint(mod) for mod in mods),
                                     tuple(inventory(mod) for mod in mods) +
                                     (inventory(dataset_ids=()),)))
    assert cell(e).terrain.score == 75
    result = e.resolve(query())
    assert result.requested.variables[0].reason == "no_relevant_product_supplied"
    assert not result.requested.eligible


def test_local_route_point_fallback_even_with_unclassified_cell():
    e = DocumentationEngine(package((dataset(),), (product(native_spacing_m=20),),
                                     (footprint(shape=box(-.02, -.02, .02, .02)),)))
    assert cell(e, 0, 0).terrain.tier == "Unclassified"
    geometry = {"type": "LineString", "coordinates": [[-.01, 0], [.01, 0]]}
    result = e.resolve(query(geometry, width=60, fallback=True))
    assert result.measure == "area_m2"
    assert not result.requested.eligible and result.supported_fallback_ids == ("fallback",)
    assert result.fallbacks[0].variables[0].qualified_fraction == 1
    assert result.requested.variables[0].candidates[0].reasons == ("native_spacing_too_coarse",)
    assert result.provenance[0].product.id == "a"
    assert not e.resolve(query(geometry, width=3000, fallback=True)).fallbacks[0].eligible
    assert e.resolve(query(geometry, spacing=20)).query_size == pytest.approx(3389500 * math.radians(.02))


def test_seam_pole_and_native_west_footprints():
    seam = DocumentationEngine(package((dataset(),), (product(),),
                                       (footprint(shape=box(359, -1, 1, 1)),), (inventory(),)))
    assert seam.resolve(query()).requested.eligible
    assert not seam.resolve(query({"type": "Point", "coordinates": [180, 0]})).requested.eligible
    assert seam.resolve(query({"type": "LineString", "coordinates": [[359.5, 0], [.5, 0]]})).requested.eligible
    ring = ((0, 89), (90, 89), (180, 89), (270, 89), (0, 89))
    polar = DocumentationEngine(package((dataset(),), (product(),), (footprint(
        shape=Polygon(type="Polygon", coordinates=(ring,))),), (inventory(),)))
    for lon in (0, 90, 270):
        assert polar.resolve(query({"type": "Point", "coordinates": [lon, 90]})).requested.eligible
    crs = product().source_crs.model_copy(update={"longitude_direction": "west", "longitude_domain": "unsigned"})
    e = DocumentationEngine(package((dataset(),), (product(source_crs=crs),),
        (footprint(shape=box(9, -1, 11, 1), status="native_geographic", transform=None),)))
    assert e.resolve(query({"type": "Point", "coordinates": [-10, 0]})).requested.eligible
    assert not e.resolve(query({"type": "Point", "coordinates": [10, 0]})).requested.eligible


def test_model_scale_time_and_compatible_variables(catalogue):
    e = DocumentationEngine(catalogue)
    req = query(max_effective_scale_m=5, acquisition_window={"start": "2024-01-01T00:00:00Z",
                                                              "end": "2024-02-01T00:00:00Z"})
    result = e.resolve(req)
    assert set(result.requested.variables[0].candidates[0].reasons) == {
        "acquisition_time_unknown", "effective_scale_too_coarse"}
    for key, expected in ((None, False), ("registered-pair", True)):
        a = product(compatibility_key=key)
        b = product("b", variables=("gradient",), compatibility_key=key)
        e = DocumentationEngine(package((dataset(),), (a, b), (footprint(), footprint("b"))))
        request = query().model_dump()
        request["requested"]["requirements"] += ({"variable": "gradient", "product_classes": ["stereo_dtm"]},)
        assert e.resolve(CapabilityQuery.model_validate(request)).requested.eligible is expected


def test_complete_mosaic_of_individual_products_requires_verified_derivative():
    e = DocumentationEngine(package((dataset(),), (product(), product("b")),
        (footprint(shape=box(-1, -1, .1, 1)), footprint("b", box(-.1, -1, 1, 1)))))
    geometry = {"type": "LineString", "coordinates": [[-.5, 0], [.5, 0]]}
    result = e.resolve(query(geometry)).requested
    assert result.variables[0].qualified_fraction == pytest.approx(1)
    assert not result.eligible and result.variables[0].reason == "no_single_product_covers_full_query"


def test_holed_footprint_and_boundary_contact_do_not_fill_gap():
    outer = box(-1, -1, 1, 1)
    inner = box(-.1, -.1, .1, .1)
    holed = Polygon(type="Polygon", coordinates=(outer.coordinates[0], inner.coordinates[0]))
    e = DocumentationEngine(package((dataset(),), (product(),), (footprint(shape=holed),), (inventory(),)))
    assert not e.resolve(query()).requested.eligible
    area = box(-.2, -.2, .2, .2).model_dump()
    result = e.resolve(query(area)).requested.variables[0]
    assert 0.74 < result.qualified_fraction < 0.76
    assert not result.covered_by_single_product
