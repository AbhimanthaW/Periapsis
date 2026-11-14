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


def groups(cells: np.ndarray, neighbours: np.ndarray, scores: np.ndarray | None = None,
           limit: int | None = None) -> list[np.ndarray]:
    """Eight-neighbour components, split at Nside-32 tiles after union."""
    members = np.flatnonzero(cells)
    if len(members) == 0:
        return []
    parent = np.arange(N, dtype=np.int32)
    source = np.repeat(members, 8)
    target = neighbours[members].reshape(-1)
    valid = (target >= 0) & (target < source) & cells[np.maximum(target, 0)]
    source, target = source[valid], target[valid]
    for _ in range(64):
        left, right = parent[source], parent[target]
        np.minimum.at(parent, np.maximum(left, right), np.minimum(left, right))
        parent = parent[parent]
        if np.array_equal(parent[source], parent[target]):
            break
    else:
        raise RuntimeError("component labels did not converge")
    key = parent[members].astype(np.int64) * 12288 + (members >> 4)
    if scores is not None and limit is not None:
        _, inverse = np.unique(key, return_inverse=True)
        count = np.bincount(inverse)
        total = np.bincount(inverse, weights=scores[members].astype(np.float64)).astype(np.uint64)
        lowest = np.full(len(count), N, dtype=np.int32)
        np.minimum.at(lowest, inverse, members)
        mean = total // count.astype(np.uint64)
        order = np.lexsort((lowest, -count, -mean.astype(np.int64)))[:limit]
        by_group = np.argsort(inverse, kind="stable")
        end = count.cumsum()
        start = end - count
        return [members[by_group[start[index]:end[index]]] for index in order]
    order = np.argsort(key, kind="stable")
    cuts = np.flatnonzero(np.diff(key[order])) + 1
    return np.split(members[order], cuts)


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
            result = connection.execute("SELECT record FROM cells WHERE nested_index=?", (index,)).fetchone()
        if not result:
            return None
        record = json.loads(zlib.decompress(result[0]))
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
        support = self._array("support", demo)
        scores = np.zeros(N, dtype=np.uint64)
        any_present = np.zeros(N, dtype=np.bool_)
        all_present = np.ones(N, dtype=np.bool_)
        effective, coverage, synthetic = {}, {}, {}
        weights = self.pack.manifest["w_int_demo" if demo else "w_int"]
        real_support = self.pack["support"]
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
        filters = self.pack["filters"]
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
        components = groups(selected, self.pack["neighbours"], scores, request.limit)
        areas = []
        method_mask = None
        if request.method:
            method_mask = np.unpackbits(filters[self.pack.manifest["filter_order"].index(request.method)], count=N).astype(bool)
        sparse = np.unpackbits(filters[self.pack.manifest["filter_order"].index("sparse")], count=N).astype(bool)
        catalogue = {}
        if components:
            indexes = np.concatenate(components)
            with closing(sqlite3.connect(self.database, uri=True)) as connection:
                for batch in np.array_split(indexes, (len(indexes) + 899) // 900):
                    placeholders = ",".join("?" for _ in batch)
                    rows = connection.execute(f"SELECT nested_index, evidence FROM catalogue WHERE nested_index IN ({placeholders})",
                                              tuple(map(int, batch)))
                    catalogue.update((index, json.loads(evidence)) for index, evidence in rows)
        for rank, cells in enumerate(components, 1):
            values = scores[cells]
            best = cells[int(np.argmax(values))]
            per_concept = {}
            for j in active:
                item = self.concepts[j]
                exact = int(support[j, best])
                value = int(effective[j][best])
                status = "DEMO" if demo and (item["status"] == "demo" or np.any(synthetic[j][cells])) else item["status"]
                flags = self.flags(item, catalogue.get(best, {}))
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
                for key, ids in catalogue.get(index, {}).items():
                    evidence.setdefault(key, set()).update(ids)
            labels = [self.features["gazetteer"][fid] for fid in sorted(evidence.get("gazetteer", ()))
                      if self.features["gazetteer"][fid].get("approval") == "Adopted by IAU"]
            label = max(labels, key=lambda x: (x.get("diameter_km") or 0, x["name"]))["name"] if labels else None
            count = self.pack["records"][cells].astype(np.uint32).sum(axis=0)
            areas.append({"rank": rank, "tile": int(cells[0]) >> 4, "cells": [f"HPX128:{i}" for i in cells],
                "best_cell": f"HPX128:{best}", "tier": tier,
                "match_mean": int(values.mean()), "match_best": int(values.max()),
                "concepts": per_concept, "records": dict(zip(("ctx", "hirise", "dtm", "crism"), map(int, count))),
                "method": "compatible" if method_mask is None or bool(method_mask[cells].any()) else "not established",
                "sparse": bool(sparse[cells].any()), "label": label,
                "point_features": {k: sorted(v) for k, v in sorted(evidence.items()) if k not in {"structures", "gazetteer_approximate_bounds"}},
                "demo": any(x["status"] == "DEMO" for x in per_concept.values())})
        base["areas"] = areas
        return base
