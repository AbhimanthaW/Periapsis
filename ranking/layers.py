"""Compile source-backed and explicitly synthetic per-cell concept support."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .inputs import N
from .ledger import load


def quant(value: float) -> int:
    return round(255 * max(0.0, min(1.0, value)))


def ramp(value: float | None, lo: float, hi: float) -> float:
    return 0.0 if value is None or value <= lo else min(1.0, (value - lo) / (hi - lo))


def compile_layers(directory: Path, with_demo: bool = False, *,
                   ice_max: float = 0.5, rocky_lo: float = 350, rocky_hi: float = 500,
                   structure_max: float = 10, bounds_max: float = 0.5):
    concepts = load()
    ids = {item["id"]: i for i, item in enumerate(concepts)}
    shape = (len(ids), N)
    real = np.zeros(shape, dtype=np.uint8)
    covered = np.zeros(shape, dtype=np.bool_)
    reported = np.zeros(shape, dtype=np.bool_)
    demo = np.zeros(shape, dtype=np.uint8)
    demo_covered = np.zeros(shape, dtype=np.bool_)
    demo_receipt = {"synthetic": True, "seed": 20261114}
    filters = {name: np.zeros(N, dtype=np.bool_) for name in
               ("polar", "volcanic", "sparse", "sample-rock", "investigate-ice", "remote-survey")}
    records = np.zeros((N, 4), dtype=np.uint16)
    latitudes = np.zeros(N, dtype=np.float32)
    unit_ages = np.zeros((N, 3), dtype=np.bool_)
    feature_ids: dict[str, dict[str, dict]] = {}
    with gzip.open(directory / "ranking-features.json.gz", "rt", encoding="utf-8") as stream:
        for key, values in json.load(stream).items():
            feature_ids[key] = {value["id"]: value for value in values}

    def put(cid, i, value=1.0, *, observed=True):
        j = ids[cid]
        real[j, i] = max(int(real[j, i]), quant(value))
        covered[j, i] = observed
        reported[j, i] = value > 0

    with gzip.open(directory / "cells-enriched.ndjson.gz", "rt", encoding="utf-8") as stream:
        for i, line in enumerate(stream):
            row = json.loads(line)
            science = row["science_at_centroid"]
            extra = row["additional_context_at_centroid"]
            units = science["geologic_units"]
            primary = units[0] if units else None
            code = primary["code"] if primary else ""
            group = primary["group"] if primary else ""
            latitudes[i] = row["latitude_deg_planetocentric"]
            filters["polar"][i] = abs(latitudes[i]) >= 60 or group == "Polar Units"
            filters["volcanic"][i] = group == "Volcanic Units"
            if primary:
                for cid, match in (
                    ("highland", group == "Highland Units"), ("massif", code in {"eNhm", "mNhm"}),
                    ("lowland", group == "Lowland Units"), ("transition", group == "Transition Units"),
                    ("outflow", code == "Hto"), ("basin", group == "Basin Units"),
                    ("impact", code == "AHi"), ("volcanic", group == "Volcanic Units"),
                    ("volcanic-edifice", code in {"Ave", "Hve", "Nve"}),
                    ("volcanic-field", code in {"lHvf", "lAvf"}),
                    ("young-volcanic", code in {"lAv", "lAvf", "Av", "Ave"}),
                    ("polar-deposits", group == "Polar Units"), ("polar-cap", code == "lApc"),
                    ("polar-dunes", code == "lApd"), ("mass-wasting", code == "Aa"),
                ):
                    put(cid, i, float(match))
                put("glacial-apron", i, 1.0 if code == "ANa" else 0.6 if code == "lAa" else 0.0)
                age = re.match(r"[NHA]+", re.sub(r"^[eml]", "", code))
                letters = set(age.group()) if age else set()
                for k, (cid, letter) in enumerate((("age-noachian", "N"), ("age-hesperian", "H"), ("age-amazonian", "A"))):
                    unit_ages[i, k] = letter in letters
                    put(cid, i, (1.0 if len(letters) == 1 else 0.6) if letter in letters else 0.0)
            measured = science["tes_night_sample_status"] == "archive_noninterpolated"
            ti = science["tes_night_thermal_inertia"] if measured else None
            albedo = extra["tes_lambert_albedo"]
            if measured and ti is not None:
                put("rocky-surface", i, ramp(ti, rocky_lo, rocky_hi))
                put("dust-mantled", i, float(ti < 100 and albedo is not None and albedo >= 0.23))
                put("dark-coarse-surface", i, float(ti >= 200 and albedo is not None and albedo < 0.15))
            elevation = row["mola_elevation_m"]
            if elevation is not None:
                put("low-elevation", i, float(elevation < -4000))
                put("high-elevation", i, float(elevation > 4000))
            swim = extra["swim_ice_consistency"] or {}
            shallow = swim.get("0_1")
            deep = [swim.get(key) for key in ("1_5", "5")]
            valid_deep = [value for value in deep if value is not None]
            valid_all = [value for value in (shallow, *deep) if value is not None]
            if valid_all:
                put("ice", i, ramp(max(valid_all), 0, ice_max))
            if shallow is not None:
                put("ice-shallow", i, ramp(shallow, 0, ice_max))
            if valid_deep:
                put("ice-deep", i, ramp(max(valid_deep), 0, ice_max))
            filters["sparse"][i] = not units or (not measured and not valid_all)
            filters["sample-rock"][i] = bool(real[ids["rocky-surface"], i] or
                (measured and ti is not None and not real[ids["dust-mantled"], i]))
            filters["investigate-ice"][i] = bool(real[ids["ice"], i] >= 128 or
                real[ids["polar-cap"], i] or real[ids["glacial-apron"], i])
            filters["remote-survey"][i] = True
            for k, value in enumerate((extra["ctx_edr_centroid_records"],
                    extra["hirise_projected_centroid_records"],
                    len(extra["hirise_dtm_centroid_product_ids"]),
                    len(science["crism_mtrdr_product_ids"]))):
                records[i, k] = min(65535, int(value or 0))

    record_counts = dict(zip(ids, ((real >= 128) & covered).sum(axis=1).tolist()))

    point_map = {"lake": "paleolakes", "chlorides": "chlorides",
                 "hydrated-minerals": "hydrated_mineral_sites", "dunes": "dunes",
                 "cave-candidate": "cave_candidates", "seismic": "marsquakes"}
    lines = {"channel": [("Fluvial", "Channel axis")], "outflow": [("Fluvial", "Outflow Channel")],
             "impact": [("Impact", "Crater rim")],
             "wrinkle-ridge": [("Tectonic", "Wrinkle ridge")], "graben": [("Tectonic", "Graben axis")],
             "pit-chain": [("Tectonic", "Pit crater chain")],
             "scarp": [("Erosional", "Scarp"), ("Volcanic", "Scarp")],
             "spiral-trough": [("Erosional", "Spiral trough")],
             "lava-flow": [("Volcanic", "Lobate flow")], "rille": [("Volcanic", "Rille")],
             "caldera": [("Volcanic", "Caldera rim")], "crater-rim": [("Impact", "Crater rim")],
             "yardang": [("Eolian", "Yardangs")]}
    bounds = {"CH": "chaos", "CM": "canyon", "FO": "graben", "LB": "canyon", "UN": "dunes"}
    with gzip.open(directory / "cell-ranking.ndjson.gz", "rt", encoding="utf-8") as stream:
        for i, line in enumerate(stream):
            evidence = json.loads(line)["evidence"]
            for cid, key in point_map.items():
                if evidence.get(key):
                    put(cid, i)
            for fid in evidence.get("paleolakes", []):
                basin = feature_ids["paleolakes"][fid]["basin_type"]
                put("lake-open-basin" if basin == "OBL" else "lake-closed-basin", i)
            line_values = evidence.get("structures", {})
            for cid, matches in lines.items():
                km = sum(float(length) for fid, length in line_values.items()
                         if (feature_ids["structures"][fid]["origin"],
                             feature_ids["structures"][fid]["interpretation"]) in matches)
                if km:
                    put(cid, i, ramp(km, 0, structure_max))
            for fid, fraction in evidence.get("gazetteer_approximate_bounds", {}).items():
                feature = feature_ids["gazetteer"][fid]
                cid = bounds.get(feature["type_code"])
                if cid:
                    put(cid, i, ramp(float(fraction), 0, bounds_max))

    if with_demo:
        # Fixed seed and fixed geographic centres. These are software fixtures,
        # never observations. Restriction to unit ages is for visual plausibility.
        rng = np.random.default_rng(20261114)
        centres = [(float(rng.uniform(0, 360)), float(rng.uniform(-55, 55))) for _ in range(10)]
        controls = {"delta": [(77.6, 18.4), (326.4, -23.9)],
                    "clays": [(340.0, 24.0)]}
        longitudes = np.empty(N, dtype=np.float32)
        with gzip.open(directory / "cells-enriched.ndjson.gz", "rt", encoding="utf-8") as stream:
            for i, line in enumerate(stream):
                longitudes[i] = json.loads(line)["longitude_deg_east"]
        lon = np.deg2rad(longitudes.astype(np.float64))
        lat = np.deg2rad(latitudes.astype(np.float64))
        for k, item in enumerate(x for x in concepts if x["status"] == "demo"):
            distance = np.full(N, np.inf)
            for c_lon, c_lat in controls.get(item["id"], [centres[k]]):
                angular = np.sin(lat) * np.sin(np.deg2rad(c_lat)) + np.cos(lat) * np.cos(np.deg2rad(c_lat)) * np.cos(lon - np.deg2rad(c_lon))
                distance = np.minimum(distance, 3389.5 * np.arccos(np.clip(angular, -1, 1)))
            footprint = distance < 250
            if item["id"] in {"delta", "alluvial-fan", "valley-network"}:
                footprint &= unit_ages[:, 0] | unit_ages[:, 1]
            if item["id"] == "clays":
                footprint &= unit_ages[:, 0]
            j = ids[item["id"]]
            demo[j, footprint] = np.rint(255 * np.exp(-0.5 * (distance[footprint] / 100) ** 2)).astype(np.uint8)
            demo_covered[j, footprint] = True
        # Reuse the repository's documented 28-cell science fixture. The
        # seeded geographic patterns above remain separate software controls.
        from marsdoc import DocumentationEngine, Package
        from marsdoc.synthetic_science import RECIPE, synthetic_scene
        package = Package(schema_version=1, package_id=RECIPE, version="1",
                          datasets=(), products=(), footprints=())
        fixture = list(synthetic_scene(DocumentationEngine(package)))
        encoded = json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode()
        demo_receipt["repository_fixture"] = {"recipe": RECIPE, "cells": len(fixture),
                                              "sha256": hashlib.sha256(encoded).hexdigest()}
        mapping = {"deltas": ("delta", "mapped_fraction"),
                   "alluvial_fans": ("alluvial-fan", "mapped_fraction"),
                   "valley_networks": ("valley-network", "length_km"),
                   "glacial_landforms": ("glacial-landform", "mapped_fraction"),
                   "crustal_magnetism": ("magnetism", "magnitude_nt"),
                   "olivine": ("olivine", "candidate_fraction_of_cell")}
        magnetic = [row["fields"]["crustal_magnetism"]["magnitude_nt"]
                    for row in fixture if row["fields"]["crustal_magnetism"] is not None]
        maximum_magnetic = max(magnetic, default=1.0)
        for row in fixture:
            index = int(row["cell_id"].split(":")[1])
            for field, (cid, metric) in mapping.items():
                values = row["fields"][field]
                if values is None:
                    continue
                value = values[metric]
                if field == "valley_networks":
                    value = ramp(value, 0, 50)
                elif field == "crustal_magnetism":
                    value = value / maximum_magnetic
                j = ids[cid]
                demo[j, index] = max(int(demo[j, index]), quant(value))
                demo_covered[j, index] = True
    return concepts, real, covered, reported, demo, demo_covered, filters, records, record_counts, demo_receipt
