"""Deterministic workload benchmark. Run once per Nside in a fresh process."""
import argparse
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path
import platform
import resource
import statistics
import sys
import time

import numpy as np
from pydantic import HttpUrl

from marsdoc import CapabilityQuery, DocumentationEngine, Package
from marsdoc.contracts import Polygon
from marsdoc.engine import _axis, _modality
from marsdoc.grid import CANONICAL

ROOT = Path(__file__).resolve().parent
ANCHORS = [(77.4, 18.4), (0, 0), (179, 24), (315, -48), (12, 62), (137, -5)]
SWATHS_PER_ANCHOR = 64
CELL_SAMPLE = 256
POINT_SAMPLE = 100_000
SYNTHETIC_SOURCE = HttpUrl("https://example.org/synthetic-benchmark")


def rss_mib():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024**2 if sys.platform == "darwin" else 1024)


def timed(operation, repeats=3):
    values = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = operation()
        values.append(time.perf_counter() - start)
    return round(statistics.median(values) * 1000, 3), result


def workload(rng, original):
    """Simulated overlapping stereo swaths. Source properties are inspired by the Jezero window."""
    source, template = original.products[0], original.footprints[0]
    dataset = original.datasets[0].model_copy(update={
        "id": "synthetic-stereo", "mission": "Synthetic", "instrument": "Synthetic",
        "archive_url": SYNTHETIC_SOURCE,
    })
    products, footprints, queries = [], [], []
    for lon, lat in ANCHORS:
        for _ in range(SWATHS_PER_ANCHOR):
            center = np.array([lon, lat]) + rng.uniform(-2, 2, size=2)
            width, length = rng.uniform(.12, .38), rng.uniform(.4, 1.2)
            angle = rng.uniform(-math.pi, math.pi)
            rotation = np.array([[math.cos(angle), -math.sin(angle)],
                                 [math.sin(angle), math.cos(angle)]])
            corners = np.array([[-width, -length], [width, -length], [width, length],
                                [-width, length], [-width, -length]]) / 2
            ring = (corners @ rotation + center).tolist()
            name = f"sim-swath-{len(products):03}"
            products.append(source.model_copy(update={
                "id": name, "dataset_id": dataset.id, "observation_extent_complete": True,
                "source_url": SYNTHETIC_SOURCE, "source_crs": CANONICAL,
                "native_spacing_m": float(rng.choice([5, 10, 20, 30, 50])),
                "provenance": ("synthetic benchmark swath",),
            }))
            footprints.append(template.model_copy(update={
                "id": name, "product_id": name, "source_url": SYNTHETIC_SOURCE,
                "transform": "synthetic canonical",
                "geometry": Polygon(type="Polygon", coordinates=(tuple(map(tuple, ring)),)),
                "note": "synthetic benchmark swath",
            }))
            points = [center - [.015, .011], center + [.017, .014]]
            queries.append({"type": "LineString", "coordinates": [item.tolist() for item in points]})
    return Package.model_validate({
        "schema_version": 1, "package_id": "synthetic-benchmark", "version": "synthetic-1",
        "datasets": (dataset.model_dump(),), "products": tuple(item.model_dump() for item in products),
        "footprints": tuple(item.model_dump() for item in footprints),
    }), queries


def run(nside):
    rng = np.random.default_rng(801026)
    real = Package.model_validate_json((ROOT / "jezero-evidence.json").read_bytes())
    data, routes = workload(rng, real)
    template = json.loads((ROOT / "jezero-route.json").read_text())
    start_rss = rss_mib()
    metrics = {}
    metrics["build_index_ms"], engine = timed(lambda: DocumentationEngine(data, nside=nside))
    grid = engine.grid
    metrics["generate_all_centroids_ms"], centroids = timed(lambda: grid.centroids(np.arange(grid.count)))
    points = np.column_stack((rng.uniform(0, 360, POINT_SAMPLE),
                             np.degrees(np.arcsin(rng.uniform(-1, 1, POINT_SAMPLE)))))
    metrics["lookup_100k_ms"], _ = timed(lambda: grid.indices(points))
    regional_points = [np.array(anchor) + rng.uniform(-4, 4, size=(250, 2)) for anchor in ANCHORS]
    samples = sorted(set(grid.indices(np.vstack(regional_points))))
    if len(samples) < CELL_SAMPLE:
        raise ValueError("benchmark regions contain too few distinct cells")
    samples = sorted(int(i) for i in rng.choice(samples, size=CELL_SAMPLE, replace=False))
    ids = [grid.identifier(i) for i in samples]
    metrics["boundary_batch_256_ms"], _ = timed(lambda: grid.boundaries(samples, step=16))
    metrics["build_256_query_charts_ms"], windows = timed(lambda: [engine._cell_window(i) for i in samples])
    metrics["intersect_256_cells_ms"], matches = timed(lambda: [engine.catalogue.match(w) for w in windows])

    def score_matched():
        summaries = []
        for window, local_matches in zip(windows, matches, strict=True):
            by_modality = defaultdict(list)
            for match in local_matches:
                by_modality[match.entry.dataset.modality].append(match)
            modalities = tuple(_modality(engine.catalogue, window, by_modality[policy.modality], policy)
                               for policy in engine.policy.modalities)
            summaries.append((_axis(modalities, "terrain", engine.policy),
                              _axis(modalities, "science_environment", engine.policy)))
        return summaries

    metrics["union_and_score_256_cells_ms"], _ = timed(score_matched)
    metrics["summarize_256_cells_ms"], summaries = timed(lambda: [engine.summarize(item) for item in ids])
    metrics["serialize_256_results_ms"], payload = timed(lambda: "\n".join(
        item.model_dump_json() for item in summaries).encode())
    route_queries = [CapabilityQuery.model_validate(template | {"geometry": routes[i]})
                     for i in rng.choice(len(routes), 128, replace=False)]
    metrics["buffer_and_resolve_128_routes_ms"], _ = timed(lambda: [engine.resolve(item) for item in route_queries])
    real_engine = DocumentationEngine(real, nside=nside)
    real_query = CapabilityQuery.model_validate(template)
    metrics["real_jezero_route_ms"], result = timed(lambda: real_engine.resolve(real_query), repeats=11)
    assert result.supported_fallback_ids == ("elevation_20m_posts",)
    return {
        "platform": platform.platform(), "python": platform.python_version(), "nside": nside,
        "cells": grid.count, "synthetic_swaths": len(data.footprints),
        "subset_cells_with_matches": sum(bool(items) for items in matches),
        "subset_product_cell_intersections": sum(map(len, matches)),
        "centroid_array_bytes": centroids.nbytes, "cell_jsonl_bytes": len(payload),
        "cell_jsonl_gzip_bytes": len(gzip.compress(payload, mtime=0)),
        "initial_peak_rss_mib": round(start_rss, 2), "peak_rss_mib": round(rss_mib(), 2),
        "timings_ms": metrics,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nside", type=int, choices=(64, 128))
    print(json.dumps(run(parser.parse_args().nside), indent=2))
