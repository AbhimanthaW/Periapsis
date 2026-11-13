"""Rebuild the deterministic synthetic mission-pack fixture."""
import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import numpy as np
from pyproj import CRS, Transformer

from contracts.pack import pin

WKT = CRS.from_proj4("+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +R=3396190 +units=m +type=crs").to_wkt()
URL = "https://example.invalid/return-window/synthetic-v1"
VERSION = {"schema_version": 1}
GRID = dict(shape=[3, 5], affine=[10, 0, 100, 0, -10, 200], bounds_m=[100, 170, 150, 200],
            pixel_reference="area", row_order="north_to_south", index_order="row_col", position_order="easting_northing")


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()


def build(directory, *, rover=False):
    directory.mkdir(parents=True, exist_ok=False)
    source = dict(id="synthetic-grid-source", version="1", kind="synthetic", recipe_id="synthetic-fixture-v1",
                  attribution="Team Periapsis synthetic fixture", native_spacing_m=10, effective_scale_m=None,
                  limitations=["Simulation only"])
    source_crs = CRS.from_wkt(WKT)
    to_geo = Transformer.from_crs(source_crs, source_crs.geodetic_crs, always_xy=True)
    ring = [(100,200),(150,200),(150,170),(140,170),(140,180),(130,180),(130,170),(100,170),(100,200)]
    grid = GRID
    recipe = "synthetic-fixture-v1"
    if rover:
        grid = dict(GRID, shape=[7, 9], bounds_m=[100, 130, 190, 200])
        ring = [(100, 200), (190, 200), (190, 130), (100, 130), (100, 200)]
        recipe = "synthetic-rover-v1"
        source["recipe_id"] = recipe
    evidence = dict(VERSION, package_id="rw-synthetic-evidence", version="1",
                    datasets=[dict(id="fixture-dataset", mission="Simulation", instrument="Simulation",
                                   modality="stereo_topography", product_class="stereo_dtm", archive_url=URL,
                                   version="1", catalogue_status="incomplete")],
                    products=[dict(id=source["id"], dataset_id="fixture-dataset", version="1", source_url=URL,
                                   source_crs=dict(body="Mars", frame="Synthetic Mars 2000 sphere", definition=WKT,
                                                   equatorial_radius_m=3396190, polar_radius_m=3396190),
                                   processing_level="simulated", readiness="usable", variables=["elevation"],
                                   native_spacing_m=10, support_extent_complete=True, observation_extent_complete=False,
                                   provenance=[f"{recipe}: software-only test"])],
                    footprints=[dict(id="fixture-support", product_id=source["id"], source_url=URL,
                                     status="canonical_verified", coverage_kind="usable_support",
                                     transform="Inverse projection of synthetic valid-cell perimeter",
                                     geometry=dict(type="Polygon", coordinates=[[to_geo.transform(*point) for point in ring]]))],
                    inventories=[])
    common = dict(evidence_id="fixture-support", objective="simulated observation", expected_artifact="simulation log entry")
    stations = dict(VERSION, stations=[dict(common, id="science-a", target_id="a", approach_cell=[2,4], dwell_s=15, priority=1),
                                       dict(common, id="survey-done", target_id="done", approach_cell=[1,4], dwell_s=1, priority=2)])
    scenario = dict(VERSION, scenario_id="synthetic-closure-v1", checkpoint=dict(id="crew", cell=[1,4]),
                    shelter=dict(id="home", cell=[1,0]), completed_task_ids=["survey-done"], remaining_s=100, reserve_s=15,
                    closures=[dict(id="mid", cells=[[1,2]]), dict(id="north", cells=[[0,2]])])
    z = np.array([[0,1,2,3,4], [0,1,2,3,4], [0,1,2,np.nan,4]], dtype="<f4")
    excluded = np.zeros(z.shape, dtype=bool)
    excluded[2,1] = True
    if rover:
        z = np.zeros(grid["shape"], dtype="<f4")
        excluded = np.zeros(z.shape, dtype=bool)
        stations["stations"][0]["approach_cell"] = [4, 5]
        stations["stations"][1]["approach_cell"] = [3, 7]
        scenario.update(scenario_id="synthetic-rover-v1", checkpoint=dict(id="crew", cell=[3, 7]),
                        shelter=dict(id="home", cell=[3, 1]), remaining_s=180,
                        closures=[dict(id="mid", cells=[[3, 4]])])
    terrain = BytesIO()
    with ZipFile(terrain, "w") as archive:
        for key, value in dict(z_m=z, valid_mask=np.isfinite(z), screen_excluded_mask=excluded).items():
            npy = BytesIO()
            np.save(npy, value, allow_pickle=False)
            archive.writestr(ZipInfo(key + ".npy"), npy.getvalue())
    files = {
        "terrain": ("terrain.npz", terrain.getvalue()),
        "sources": ("source-manifest.json", json_bytes(dict(VERSION, sources=[source]))),
        "evidence": ("evidence.json", json_bytes(evidence)),
        "stations": ("stations.json", json_bytes(stations)),
        "scenario": ("scenario.json", json_bytes(scenario)),
    }
    for name, raw in files.values():
        (directory / name).write_bytes(raw)
    reasons = {4: ("not_applicable", "Synthetic terrain"), 6: ("not_applicable", "Synthetic science task"),
               10: ("not_evaluated", "Loader acceptance is recorded externally")}
    gates = {f"G{i}": dict(zip(("state", "reason"), reasons.get(i, ("pass_fixture", "Synthetic fixture control"))))
             for i in range(1, 11)}
    site = dict(VERSION, pack_id="rw-synthetic-rover" if rover else "rw-synthetic", pack_version="1.0.0", region_id="synthetic-grid",
                classification="synthetic", build_id=recipe, processed_at="2026-11-10T00:00:00Z",
                capabilities=["routing_simulation"], gates=gates, omissions=["Tactical routing and real science are disabled"],
                grid=grid, reference=dict(source_crs_wkt=WKT, local_crs_wkt=WKT, horizontal_unit="m", vertical_unit="m",
                                          vertical_reference="synthetic-zero-plane-v1", native_spacing_m=10),
                artifacts={role: pin(name, raw) for role, (name, raw) in files.items()})
    (directory / "site.json").write_bytes(json_bytes(site))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--rover", action="store_true", help="generate a rover-capable pack with interior endpoints")
    args = parser.parse_args()
    build(args.directory, rover=args.rover)
