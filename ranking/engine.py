"""Objective scoring, evidence states, filters, groups and area ranking."""
from __future__ import annotations

import base64
import gzip
import json
import re
import sqlite3
import zlib
from contextlib import closing

import numpy as np

from .inputs import N
from .ledger import load
from .lexicon import Parser, effective_negations
from .pack import Pack


SWIM_CONCEPTS = {"ice", "ice-shallow", "ice-deep"}
BOUND_CONCEPTS = {"CH": "chaos", "CM": "canyon", "FO": "graben", "LB": "canyon", "UN": "dunes"}


def evidence_state(item, covered, support):
    if not covered:
        return "Not reported" if item["status"] == "catalogue" else "Not evaluated"
    return "Present" if support >= 128 else "Weak" if support else "Absent"


def tile_cross_edges(neighbours: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    source = np.repeat(np.arange(N, dtype=np.int32), 8)
    target = neighbours.reshape(-1)
    valid = (target >= 0) & (target < source) & ((target >> 4) != (source >> 4))
    return source[valid], target[valid]


def _union(parent: np.ndarray, source: np.ndarray, target: np.ndarray) -> np.ndarray:
    while source.size:
        left, right = parent[source], parent[target]
        if np.array_equal(left, right):
            break
        np.minimum.at(parent, np.maximum(left, right), np.minimum(left, right))
        parent = parent[parent]
    return parent


def groups(cells: np.ndarray, neighbours: np.ndarray, scores: np.ndarray | None = None,
           limit: int | None = None,
           cross_edges: tuple[np.ndarray, np.ndarray] | None = None) -> list[np.ndarray]:
    """Eight-neighbour components, split at Nside-32 tiles after union."""
    members = np.flatnonzero(cells)
    if len(members) == 0:
        return []
    # A fully selected Nside-32 tile is already internally connected. Treat
    # its 16 cells as one node during the global union, then restore cell IDs
    # when splitting components at tile boundaries below.
    full_tiles = np.flatnonzero(cells.reshape(-1, 16).all(axis=1))
    if len(members) >= 80000 and len(full_tiles) >= 512:
        local = np.arange(N, dtype=np.int32)
        local.reshape(-1, 16)[full_tiles] = full_tiles[:, None] * 16
        full_mask = np.zeros(N // 16, dtype=bool)
        full_mask[full_tiles] = True
        partial = members[~full_mask[members >> 4]]
        source = np.repeat(partial, 8)
        target = neighbours[partial].reshape(-1)
        valid = (target >= 0) & (target < source) & ((target >> 4) == (source >> 4)) & cells[np.maximum(target, 0)]
        local = _union(local, source[valid], target[valid])
        edge_source, edge_target = cross_edges if cross_edges is not None else tile_cross_edges(neighbours)
        valid = cells[edge_source] & cells[edge_target]
        parent = _union(np.arange(N, dtype=np.int32), local[edge_source[valid]], local[edge_target[valid]])
        key = parent[local[members]].astype(np.int64) * 12288 + (members >> 4)
    else:
        compressed = len(full_tiles) >= 128
        if compressed:
            node = np.arange(N, dtype=np.int32) + 12288
            node.reshape(-1, 16)[full_tiles] = full_tiles[:, None]
            member_nodes = node[members]
            parent = np.arange(N + 12288, dtype=np.int32)
        else:
            node = None
            member_nodes = members
            parent = np.arange(N, dtype=np.int32)
        source = np.repeat(member_nodes, 8)
        target = neighbours[members].reshape(-1)
        target_node = node[np.maximum(target, 0)] if compressed else target
        valid = (target >= 0) & (target_node < source) & cells[np.maximum(target, 0)]
        parent = _union(parent, source[valid], target_node[valid])
        key = parent[member_nodes].astype(np.int64) * 12288 + (members >> 4)
    order = np.argsort(key, kind="stable")
    ordered = members[order]
    starts = np.concatenate(([0], np.flatnonzero(np.diff(key[order])) + 1))
    if scores is not None and limit is not None:
        ends = np.concatenate((starts[1:], [len(ordered)]))
        count = ends - starts
        total = np.add.reduceat(scores[ordered], starts, dtype=np.uint64)
        mean = total // count.astype(np.uint64)
        ranked = np.lexsort((ordered[starts], -count, -mean.astype(np.int64)))[:limit]
        return [ordered[starts[index]:ends[index]] for index in ranked]
    return np.split(ordered, starts[1:])


class Engine:
    def __init__(self, pack: Pack):
        self.pack = pack
        self.concepts = load(pack.directory / "concepts.json")
        if [x["id"] for x in self.concepts] != pack.manifest["concept_order"]:
            raise ValueError("pack concept ledger differs from code")
        self.ids = {item["id"]: i for i, item in enumerate(self.concepts)}
        self.parser = Parser(pack.directory / "lexicon.json", concepts=self.concepts)
        self.broader = [tuple(self.ids[parent] for parent in self.ancestors(item["id"]))
                        if item["id"] not in SWIM_CONCEPTS else () for item in self.concepts]
        self.idf = dict(zip(self.ids, pack.manifest["idf"]))
        self.demo_idf = dict(zip(self.ids, pack.manifest["idf_demo"]))
        with gzip.open(pack.directory / "ranking-features.json.gz", "rt", encoding="utf-8") as stream:
            self.features = {key: {value["id"]: value for value in values}
                             for key, values in json.load(stream).items()}
        with gzip.open(pack.directory / "catalogue-context.json.gz", "rt", encoding="utf-8") as stream:
            self.catalogue = {int(index): evidence for index, evidence in json.load(stream).items()}
        self.neighbours = np.asarray(pack["neighbours"])
        self.records = np.asarray(pack["records"])
        self.real_support = np.asarray(pack["support"])
        self.cross_edges = tile_cross_edges(self.neighbours)
        self.database = (pack.directory / "cells.sqlite").resolve().as_uri() + "?mode=ro"

    def ancestors(self, cid: str) -> list[str]:
        found, pending = set(), list(self.concepts[self.ids[cid]]["broader"])
        while pending:
            parent = pending.pop()
            if parent not in found:
                found.add(parent)
                pending.extend(self.concepts[self.ids[parent]]["broader"])
        return sorted(found)

    def _array(self, name, demo):
        return self.pack[f"{name}_demo"] if demo and self.pack.manifest["synthetic_layers"] else self.pack[name]

    def _coverage(self, row, demo=False):
        return np.unpackbits(self._array("covered", demo)[row], count=N).astype(bool)

    def flags(self, item, evidence):
        flags = [item["flag"]] if "flag" in item else []
        for fid in evidence.get("gazetteer_approximate_bounds", ()):
            feature = self.features["gazetteer"].get(fid)
            if feature and BOUND_CONCEPTS.get(feature["type_code"]) == item["id"]:
                if "Approximate published bounds" not in flags:
                    flags.append("Approximate published bounds")
                break
        return flags

    def detail(self, cell_id: str):
        if not re.fullmatch(r"HPX128:(?:0|[1-9][0-9]{0,5})", cell_id):
            return None
        index = int(cell_id[7:])
        if index >= N:
            return None
        with closing(sqlite3.connect(self.database, uri=True)) as connection:
            result = connection.execute("SELECT record FROM blocks WHERE block_id=?", (index // 1024,)).fetchone()
        if not result:
            return None
        lines = zlib.decompress(result[0]).splitlines()
        if index % 1024 >= len(lines):
            return None
        record = json.loads(lines[index % 1024])
        coverage = (self.pack["covered"][:, index // 8] & (128 >> (index % 8))) != 0
        states = {}
        for j, item in enumerate(self.concepts):
            if item["status"] in {"unsupported", "demo"}:
                continue
            val = int(self.pack["support"][j, index])
            states[item["id"]] = {"state": evidence_state(item, coverage[j], val),
                                  "support": round(val / 255, 4),
                                  "flags": self.flags(item, record["sourced_catalogue_context"])}
        return {"record": record, "concepts": states,
                "pack": {"version": self.pack.manifest["version"], "sha256": self.pack.sha256}}

    def rank(self, request, *, parsed=None):
        demo = bool(request.include_demo and self.pack.manifest["synthetic_layers"])
        if parsed is None:
            parsed = self.parser.parse(request.objective, include_demo=demo,
                                       idf=self.demo_idf if demo else self.idf)
        active = sorted(self.ids[item["id"]] for item in parsed["concepts"])
        identity = {"version": self.pack.manifest["version"], "sha256": self.pack.sha256,
                    "release": self.pack.manifest["release"],
                    "synthetic_layers": self.pack.manifest["synthetic_layers"], "demo_enabled": demo}
        empty_heat = base64.b64encode(bytes(12288)).decode()
        base = {"schema_version": 1, "request_id": request.request_id, "pack": identity,
                "parse": parsed, "abstain": not active,
                "counts": {"direct_cells": 0, "partial_cells": 0, "thematic_cells": 0, "excluded": {}},
                "areas": [], "heat_nside32": empty_heat}
        if not active:
            return base
        support = np.asarray(self._array("support", demo))
        scores = np.zeros(N, dtype=np.uint64)
        any_present = np.zeros(N, dtype=np.bool_)
        all_present = np.ones(N, dtype=np.bool_)
        effective, coverage, synthetic = {}, {}, {}
        weights = self.pack.manifest["w_int_demo" if demo else "w_int"]
        real_support = self.real_support
        real_weights = self.pack.manifest["w_int"]
        for j in active:
            values = support[j]
            covered = self._coverage(j, demo)
            value = np.where(covered, values, 0)
            # A broader match is affinity only, and does not evaluate the layer.
            for parent in self.broader[j]:
                value = np.maximum(value, np.rint(support[parent] * np.float32(0.35)).astype(np.uint8))
            effective[j], coverage[j] = value, covered
            if demo:
                baseline = real_support[j]
                for parent in self.broader[j]:
                    baseline = np.maximum(baseline, np.rint(real_support[parent] * np.float32(0.35)).astype(np.uint8))
                synthetic[j] = (values > real_support[j]) | (value > baseline) | ((value > 0) & (weights[j] != real_weights[j]))
            scores += np.uint64(weights[j]) * value
            hit = covered & (values >= 128)
            any_present |= hit
            all_present &= hit
        direct = all_present & (scores > 0)
        partial = any_present & ~direct & (scores > 0)
        thematic = (scores > 0) & ~direct & ~partial
        excluded = {}
        filters = np.asarray(self.pack["filters"])
        filter_order = self.pack.manifest["filter_order"]
        eligible = direct | partial | thematic
        for reason in sorted(set(request.exclude)):
            mask = np.unpackbits(filters[filter_order.index(reason)], count=N).astype(bool)
            excluded[reason] = int((mask & eligible).sum())
            direct &= ~mask
            partial &= ~mask
            thematic &= ~mask
        for cid in effective_negations(parsed, demo):
            j = self.ids[cid]
            mask = (support[j] >= 128) & self._coverage(j, demo)
            excluded[f"not {cid}"] = int((mask & eligible).sum())
            direct &= ~mask
            partial &= ~mask
            thematic &= ~mask
        scores[~(direct | partial | thematic)] = 0
        base["counts"] = {"direct_cells": int(direct.sum()), "partial_cells": int(partial.sum()),
                          "thematic_cells": int(thematic.sum()), "excluded": excluded}
        selected = direct if direct.any() else partial if partial.any() else thematic
        tier = "Direct" if direct.any() else "Partial" if partial.any() else "Thematic"
        maximum = sum(int(weights[j]) * 255 for j in active)
        tile_max = scores.reshape(-1, 16).max(axis=1)
        heat = np.minimum(255, (tile_max * 255 // max(1, maximum))).astype(np.uint8)
        base["heat_nside32"] = base64.b64encode(heat.tobytes()).decode()
        components = groups(selected, self.neighbours, scores, request.limit, self.cross_edges)
        areas = []
        method_mask = None
        if request.method:
            method_mask = np.unpackbits(filters[self.pack.manifest["filter_order"].index(request.method)], count=N).astype(bool)
        sparse = np.unpackbits(filters[self.pack.manifest["filter_order"].index("sparse")], count=N).astype(bool)
        for rank, cells in enumerate(components, 1):
            values = scores[cells]
            best_offset = int(np.argmax(values))
            best = cells[best_offset]
            per_concept = {}
            for j in active:
                item = self.concepts[j]
                exact = int(support[j, best])
                value = int(effective[j][best])
                status = "DEMO" if demo and (item["status"] == "demo" or np.any(synthetic[j][cells])) else item["status"]
                flags = self.flags(item, self.catalogue.get(int(best), {}))
                if status == "DEMO":
                    flags.append("Synthetic data enabled for this concept")
                per_concept[item["id"]] = {
                    "state": evidence_state(item, coverage[j][best], exact), "support": round(exact / 255, 4),
                    "relation": "broader" if value > exact else "exact", "status": status, "flags": flags,
                }
                if value > exact:
                    per_concept[item["id"]]["broader_support"] = round(value / 255, 4)
            evidence = {}
            for index in cells:
                for key, ids in self.catalogue.get(int(index), {}).items():
                    evidence.setdefault(key, set()).update(ids)
            labels = [self.features["gazetteer"][fid] for fid in sorted(evidence.get("gazetteer", ()))
                      if self.features["gazetteer"][fid].get("approval") == "Adopted by IAU"]
            label = max(labels, key=lambda x: (x.get("diameter_km") or 0, x["name"]))["name"] if labels else None
            count = self.records[cells].sum(axis=0, dtype=np.uint32)
            areas.append({"rank": rank, "tile": int(cells[0]) >> 4, "cells": [f"HPX128:{i}" for i in cells],
                "best_cell": f"HPX128:{best}", "tier": tier,
                "match_mean": int(values.sum(dtype=np.uint64) // len(values)), "match_best": int(values[best_offset]),
                "concepts": per_concept, "records": dict(zip(("ctx", "hirise", "dtm", "crism"), map(int, count))),
                "method": "compatible" if method_mask is None or bool(method_mask[cells].any()) else "not established",
                "sparse": bool(sparse[cells].any()), "label": label,
                "point_features": {k: sorted(v) for k, v in sorted(evidence.items()) if k not in {"structures", "gazetteer_approximate_bounds"}},
                "demo": any(x["status"] == "DEMO" for x in per_concept.values())})
        base["areas"] = areas
        return base
