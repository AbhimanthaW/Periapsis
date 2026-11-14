"""Compile source-backed and explicitly synthetic per-cell concept support."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
from contextlib import nullcontext
from pathlib import Path

import numpy as np

from .inputs import N
from .ledger import load


CACHE_RULE_VERSION = "ranking-layers-v5"
DEMO_CENTRES = 8
DEMO_SEPARATION_KM = 500
DEMO_DELTA_CLEARANCE_KM = 600
DEMO_FIELD_SOURCES = 16
DEMO_FIELD_ALTITUDE_KM = 150
LEGACY_DEMO = ("delta", "alluvial-fan", "valley-network", "clays", "sulfates", "carbonates",
               "silica", "glacial-landform", "magnetism", "olivine")


def _cache_key(directory: Path, layer: str, sources: tuple[str, ...], parameters: dict) -> str:
    receipt = {"layer": layer, "rules": CACHE_RULE_VERSION,
               "ledger": hashlib.sha256(Path(__file__).with_name("concepts.json").read_bytes()).hexdigest(),
               "sources": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in sources},
               "parameters": parameters}
    return hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load_cache(root: Path, layer: str, key: str) -> dict | None:
    path = root / f"{layer}-{key}.npz"
    if not path.exists():
        return None
    try:
        with np.load(path, allow_pickle=False) as stored:
            return {name: stored[name] for name in stored.files}
    except (OSError, ValueError):
        return None


def _save_cache(root: Path, layer: str, key: str, **arrays):
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{layer}-{key}.npz"
    with tempfile.NamedTemporaryFile(dir=root, suffix=".npz", delete=False) as stream:
        temporary = Path(stream.name)
        np.savez_compressed(stream, **arrays)
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def quant(value: float) -> int:
    return round(255 * max(0.0, min(1.0, value)))


def ramp(value: float | None, lo: float, hi: float) -> float:
    return 0.0 if value is None or value <= lo else min(1.0, (value - lo) / (hi - lo))


def compile_layers(directory: Path, with_demo: bool = False, *,
                   ice_max: float = 0.5, rocky_lo: float = 350, rocky_hi: float = 500,
                   structure_max: float = 10, bounds_max: float = 0.5):
    concepts = load()
    cache_root = directory.parent / "ranking-layer-cache"
    keys = {
        "base": _cache_key(directory, "base", ("cells-enriched.ndjson.gz",),
                           {"ice_max": ice_max, "rocky_lo": rocky_lo, "rocky_hi": rocky_hi}),
        "catalogue": _cache_key(directory, "catalogue",
                                ("cell-ranking.ndjson.gz", "ranking-features.json.gz"),
                                {"structure_max": structure_max, "bounds_max": bounds_max}),
    }
    if with_demo:
        from marsdoc import synthetic_science
        keys["demo"] = _cache_key(directory, "demo", ("cells-enriched.ndjson.gz",),
                                  {"seed": 20261114, "fixture": "synthetic-science-v1",
                                   "fixture_code_sha256": hashlib.sha256(
                                       Path(synthetic_science.__file__).read_bytes()).hexdigest()})
    ids = {item["id"]: i for i, item in enumerate(concepts)}
    shape = (len(ids), N)
    real = np.zeros(shape, dtype=np.uint8)
    covered = np.zeros(shape, dtype=np.bool_)
    reported = np.zeros(shape, dtype=np.bool_)
    demo = np.zeros(shape, dtype=np.uint8)
    demo_covered = np.zeros(shape, dtype=np.bool_)
    demo_receipt = {"synthetic": True, "seed": 20261114}
    demo_cache = _load_cache(cache_root, "demo", keys["demo"]) if with_demo else None
    if demo_cache is not None:
        demo[:] = demo_cache["support"]
        demo_covered[:] = demo_cache["covered"]
        demo_receipt = json.loads(str(demo_cache["receipt"].item()))
    filters = {name: np.zeros(N, dtype=np.bool_) for name in
               ("polar", "volcanic", "sparse", "sample-rock", "investigate-ice", "remote-survey")}
    records = np.zeros((N, 4), dtype=np.uint16)
    latitudes = np.zeros(N, dtype=np.float32)
    unit_ages = np.zeros((N, 3), dtype=np.bool_)
    feature_ids: dict[str, dict[str, dict]] = {}
    with gzip.open(directory / "ranking-features.json.gz", "rt", encoding="utf-8") as stream:
        for key, values in json.load(stream).items():
            feature_ids[key] = {value["id"]: value for value in values}

    target_real, target_covered, target_reported = real, covered, reported

    def put(cid, i, value=1.0, *, observed=True):
        j = ids[cid]
        target_real[j, i] = max(int(target_real[j, i]), quant(value))
        target_covered[j, i] = observed
        target_reported[j, i] = value > 0

    base_cache = _load_cache(cache_root, "base", keys["base"])
    if base_cache is not None:
        real[:] = base_cache["support"]
        covered[:] = base_cache["covered"]
        reported[:] = base_cache["reported"]
        records[:] = base_cache["records"]
        latitudes[:] = base_cache["latitudes"]
        unit_ages[:] = base_cache["unit_ages"]
        for name in filters:
            filters[name][:] = base_cache[f"filter_{name}"]
    source = (gzip.open(directory / "cells-enriched.ndjson.gz", "rt", encoding="utf-8")
              if base_cache is None else nullcontext(()))
    with source as stream:
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

    if base_cache is None:
        _save_cache(cache_root, "base", keys["base"], support=real, covered=covered,
                    reported=reported, records=records, latitudes=latitudes, unit_ages=unit_ages,
                    **{f"filter_{name}": value for name, value in filters.items()})
    record_counts = dict(zip(ids, ((real >= 128) & covered).sum(axis=1).tolist()))
    catalogue_real = np.zeros_like(real)
    catalogue_covered = np.zeros_like(covered)
    catalogue_reported = np.zeros_like(reported)
    target_real, target_covered, target_reported = catalogue_real, catalogue_covered, catalogue_reported

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
    catalogue_cache = _load_cache(cache_root, "catalogue", keys["catalogue"])
    if catalogue_cache is not None:
        catalogue_real[:] = catalogue_cache["support"]
        catalogue_covered[:] = catalogue_cache["covered"]
        catalogue_reported[:] = catalogue_cache["reported"]
    source = (gzip.open(directory / "cell-ranking.ndjson.gz", "rt", encoding="utf-8")
              if catalogue_cache is None else nullcontext(()))
    with source as stream:
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

    if catalogue_cache is None:
        _save_cache(cache_root, "catalogue", keys["catalogue"], support=catalogue_real,
                    covered=catalogue_covered, reported=catalogue_reported)
    real = np.maximum(real, catalogue_real)
    covered |= catalogue_covered
    reported |= catalogue_reported

    if with_demo and demo_cache is None:
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
        # Additional fixed-seed delta controls make the headline DEMO objective
        # large enough to exercise a top-20 rank. They are synthetic locations,
        # selected from mapped old terrain only for a plausible software test.
        old = np.flatnonzero(unit_ages[:, 0] & (np.abs(latitudes) < 55))
        for index in rng.permutation(old):
            point = (float(longitudes[index]), float(latitudes[index]))
            separation = [3389.5 * np.arccos(np.clip(
                np.sin(lat[index]) * np.sin(np.deg2rad(y))
                + np.cos(lat[index]) * np.cos(np.deg2rad(y)) * np.cos(lon[index] - np.deg2rad(x)),
                -1, 1)) for x, y in controls["delta"]]
            if min(separation) >= 500:
                controls["delta"].append(point)
            if len(controls["delta"]) == 8:
                break
        if len(controls["delta"]) != 8:
            raise ValueError("unable to place the fixed-seed DEMO delta controls")
        demo_receipt["delta_controls"] = controls["delta"]

        def separation_km(index, points):
            return 3389.5 * np.arccos(np.clip(
                np.sin(lat[index]) * np.sin(np.deg2rad([y for _, y in points]))
                + np.cos(lat[index]) * np.cos(np.deg2rad([y for _, y in points]))
                * np.cos(lon[index] - np.deg2rad([x for x, _ in points])), -1, 1))

        # Densify the legacy DEMO layers to DEMO_CENTRES fixed-seed centres so
        # each can fill a top-20 ranking. The first centre is unchanged. New
        # centres are drawn after the delta controls, so the delta stream and
        # its pinned cells are unchanged, and they stay DEMO_DELTA_CLEARANCE_KM
        # from every delta control so the headline DEMO objective is untouched.
        # Glacial landforms, magnetism and the seven formerly unsupported layers use
        # a second fixed stream so the legacy draws keep their order.
        # Masks are for visual plausibility only, never evidence.
        ages_any = unit_ages[:, 0] | unit_ages[:, 1]
        abs_lat = np.abs(latitudes)
        everywhere = np.ones(N, dtype=np.bool_)
        footprint_mask = {
            "delta": ages_any, "alluvial-fan": ages_any, "valley-network": ages_any,
            "clays": unit_ages[:, 0], "hydrothermal": ages_any,
            # Levy et al. (2014) mapped these landforms within roughly 30-50 degrees.
            "glacial-landform": (abs_lat >= 30) & (abs_lat <= 50),
            "periglacial": (abs_lat >= 35) & (abs_lat <= 58),
            "ocean": real[ids["lowland"]] >= 128,
        }
        demo_ids = [x["id"] for x in concepts if x["status"] == "demo"]
        extended = [cid for cid in demo_ids if cid not in LEGACY_DEMO]

        def place(cid, stream, points):
            eligible = footprint_mask.get(cid, everywhere) & (abs_lat < 55)
            for index in stream.permutation(np.flatnonzero(eligible)):
                if ((not points or separation_km(index, points).min() >= DEMO_SEPARATION_KM)
                        and separation_km(index, controls["delta"]).min() >= DEMO_DELTA_CLEARANCE_KM):
                    points.append((float(longitudes[index]), float(latitudes[index])))
                if len(points) == DEMO_CENTRES:
                    break
            if len(points) != DEMO_CENTRES:
                raise ValueError(f"unable to place the fixed-seed DEMO controls for {cid}")
            controls[cid] = points

        for k, cid in enumerate(LEGACY_DEMO):
            if cid not in {"delta", "glacial-landform", "magnetism"}:
                place(cid, rng, controls.get(cid, [centres[k]]))
        second = np.random.default_rng([20261114, 2])
        for cid in ("glacial-landform", *extended):
            place(cid, second, [])
        demo_receipt["seeded_controls"] = {cid: points for cid, points in sorted(controls.items())}
        for cid in demo_ids:
            if cid == "magnetism":
                continue
            distance = np.full(N, np.inf)
            for c_lon, c_lat in controls[cid]:
                angular = np.sin(lat) * np.sin(np.deg2rad(c_lat)) + np.cos(lat) * np.cos(np.deg2rad(c_lat)) * np.cos(lon - np.deg2rad(c_lon))
                distance = np.minimum(distance, 3389.5 * np.arccos(np.clip(angular, -1, 1)))
            footprint = (distance < 250) & footprint_mask.get(cid, everywhere)
            j = ids[cid]
            demo[j, footprint] = np.rint(255 * np.exp(-0.5 * (distance[footprint] / 100) ** 2)).astype(np.uint8)
            demo_covered[j, footprint] = True
        # A global synthetic field, because a real crustal-field model would
        # give a value in every cell. Buried sources sit under old terrain.
        # Each adds a dipole-like magnitude K h / r^3 seen from DEMO_FIELD_ALTITUDE_KM.
        sources = []
        for index in second.permutation(np.flatnonzero(unit_ages[:, 0] & (abs_lat < 70))):
            if not sources or separation_km(index, [s[:2] for s in sources]).min() >= 600:
                sources.append((float(longitudes[index]), float(latitudes[index]),
                                round(float(second.uniform(0.5, 1.5)), 4)))
            if len(sources) == DEMO_FIELD_SOURCES:
                break
        field = np.zeros(N)
        h = DEMO_FIELD_ALTITUDE_KM
        for c_lon, c_lat, strength in sources:
            angular = np.sin(lat) * np.sin(np.deg2rad(c_lat)) + np.cos(lat) * np.cos(np.deg2rad(c_lat)) * np.cos(lon - np.deg2rad(c_lon))
            d = 3389.5 * np.arccos(np.clip(angular, -1, 1))
            field += strength * h ** 3 / (d ** 2 + h ** 2) ** 1.5
        reference = float(np.quantile(field, 0.99))
        j = ids["magnetism"]
        demo[j] = np.rint(255 * np.clip(field / reference, 0, 1)).astype(np.uint8)
        demo_covered[j] = True
        demo_receipt["magnetism_sources"] = sources
        demo_receipt["magnetism_altitude_km"] = h
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
    if with_demo and demo_cache is None:
        _save_cache(cache_root, "demo", keys["demo"], support=demo, covered=demo_covered,
                    receipt=np.asarray(json.dumps(demo_receipt, sort_keys=True)))
    return concepts, real, covered, reported, demo, demo_covered, filters, records, record_counts, demo_receipt, keys
