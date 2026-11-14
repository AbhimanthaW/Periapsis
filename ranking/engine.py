"""Objective scoring, evidence states, filters, groups and area ranking."""
from __future__ import annotations

import base64
import gzip
import json
import sqlite3
import zlib
from functools import lru_cache

import numpy as np

from .inputs import N
from .ledger import load
from .lexicon import Parser
from .pack import Pack


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
        return [members[inverse == index] for index in order]
    order = np.argsort(key, kind="stable")
    cuts = np.flatnonzero(np.diff(key[order])) + 1
    return np.split(members[order], cuts)


class Engine:
    def __init__(self, pack: Pack):
        self.pack = pack
        self.concepts = load()
        if [x["id"] for x in self.concepts] != pack.manifest["concept_order"]:
            raise ValueError("pack concept ledger differs from code")
        self.ids = {item["id"]: i for i, item in enumerate(self.concepts)}
        self.parser = Parser()
        self.idf = dict(zip(self.ids, pack.manifest["idf"]))
        self.demo_idf = dict(zip(self.ids, pack.manifest["idf_demo"]))
        with gzip.open(pack.directory / "ranking-features.json.gz", "rt", encoding="utf-8") as stream:
            self.features = {key: {value["id"]: value for value in values}
                             for key, values in json.load(stream).items()}
        self.database = pack.directory / "cells.sqlite"

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

    def detail(self, cell_id: str):
        if not cell_id.startswith("HPX128:") or not cell_id[7:].isdigit():
            return None
        index = int(cell_id[7:])
        if index >= N:
            return None
        with sqlite3.connect(self.database) as connection:
            result = connection.execute("SELECT record FROM cells WHERE nested_index=?", (index,)).fetchone()
        if not result:
            return None
        states = {}
        support = self.pack["support"]
        for j, item in enumerate(self.concepts):
            if item["status"] == "unsupported":
                continue
            cov = bool(np.unpackbits(self.pack["covered"][j], count=N)[index])
            val = int(support[j, index])
            state = "Not evaluated" if not cov else "Present" if val >= 128 else "Weak" if val else "Absent"
            if item["status"] == "catalogue" and not cov:
                state = "Not reported"
            states[item["id"]] = {"state": state, "support": round(val / 255, 4)}
        return {"record": json.loads(zlib.decompress(result[0])), "concepts": states,
                "pack": {"version": self.pack.manifest["version"], "sha256": self.pack.sha256}}

    def rank(self, request):
        demo = bool(request.include_demo and self.pack.manifest["synthetic_layers"])
        parsed = self.parser.parse(request.objective, include_demo=demo,
                                   idf=self.demo_idf if demo else self.idf)
        active = [self.ids[item["id"]] for item in parsed["concepts"]]
        identity = {"version": self.pack.manifest["version"], "sha256": self.pack.sha256,
                    "release": self.pack.manifest["release"],
                    "synthetic_layers": self.pack.manifest["synthetic_layers"]}
        empty_heat = base64.b64encode(bytes(12288)).decode()
        base = {"schema_version": 1, "request_id": request.request_id, "pack": identity,
                "parse": parsed, "abstain": not active,
                "counts": {"direct_cells": 0, "partial_cells": 0, "excluded": {}},
                "areas": [], "heat_nside32": empty_heat}
        if not active:
            return base
        support = self._array("support", demo)
        scores = np.zeros(N, dtype=np.uint64)
        present = np.zeros(N, dtype=np.uint8)
        all_present = np.ones(N, dtype=np.bool_)
        effective = {}
        for j in active:
            values = support[j]
            weights = self.pack.manifest["w_int_demo"] if demo else self.pack.manifest["w_int"]
            broader = np.zeros(N, dtype=np.uint8)
            for parent in self.ancestors(self.concepts[j]["id"]):
                broader = np.maximum(broader, np.rint(support[self.ids[parent]].astype(np.float32) * 0.35).astype(np.uint8))
            value = np.maximum(values, broader)
            effective[j] = value
            scores += np.uint64(weights[j]) * value.astype(np.uint64)
            covered = self._coverage(j, demo)
            hit = covered & (values >= 128)
            present += hit.astype(np.uint8)
            all_present &= hit
        direct = all_present & (scores > 0)
        partial = (present > 0) & ~direct & (scores > 0)
        thematic = (scores > 0) & ~direct & ~partial
        excluded = {}
        filters = self.pack["filters"]
        for reason in request.exclude:
            mask = np.unpackbits(filters[self.pack.manifest["filter_order"].index(reason)], count=N).astype(bool)
            excluded[reason] = int((mask & (direct | partial | thematic)).sum())
            direct &= ~mask; partial &= ~mask; thematic &= ~mask
        for item in parsed["negated"]:
            j = self.ids[item["id"]]
            mask = support[j] >= 128
            excluded[f"not {item['id']}"] = int((mask & (direct | partial | thematic)).sum())
            direct &= ~mask; partial &= ~mask; thematic &= ~mask
        scores[~(direct | partial | thematic)] = 0
        base["counts"] = {"direct_cells": int(direct.sum()), "partial_cells": int(partial.sum()),
                          "thematic_cells": int(thematic.sum()), "excluded": excluded}
        selected = direct if direct.any() else partial if partial.any() else thematic
        tier = "Direct" if direct.any() else "Partial" if partial.any() else "Thematic"
        maximum = sum(int(self.pack.manifest["w_int_demo" if demo else "w_int"][j]) * 255 for j in active)
        tile_max = scores.reshape(-1, 16).max(axis=1)
        heat = np.minimum(255, (tile_max * 255 // max(1, maximum))).astype(np.uint8)
        base["heat_nside32"] = base64.b64encode(heat.tobytes()).decode()
        components = groups(selected, self.pack["neighbours"], scores, request.limit)
        areas = []
        method_mask = None
        if request.method:
            method_mask = np.unpackbits(filters[self.pack.manifest["filter_order"].index(request.method)], count=N).astype(bool)
        sparse = np.unpackbits(filters[self.pack.manifest["filter_order"].index("sparse")], count=N).astype(bool)
        with sqlite3.connect(self.database) as connection:
            for cells in components:
                values = scores[cells]
                best = cells[int(np.argmax(values))]
                per_concept = {}
                for j in active:
                    item = self.concepts[j]
                    exact = int(support[j, best]); v = int(effective[j][best]); cov = self._coverage(j, demo)[best]
                    relation = "broader" if v > exact else "exact"
                    baseline = int(self.pack["support"][j, best])
                    for parent in self.ancestors(item["id"]):
                        baseline = max(baseline, round(0.35 * int(self.pack["support"][self.ids[parent], best])))
                    synthetic = bool(demo and v > baseline)
                    state = "Not evaluated" if not cov and not v else "Present" if exact >= 128 else "Weak" if v else "Absent"
                    if item["status"] == "catalogue" and not cov and not v:
                        state = "Not reported"
                    per_concept[item["id"]] = {"state": state, "support": round(v / 255, 4),
                        "relation": relation, "status": "DEMO" if synthetic else item["status"],
                        "flags": ([item["flag"]] if "flag" in item else []) + (["Synthetic support"] if synthetic else [])}
                evidence = {}
                for index in cells:
                    row = connection.execute("SELECT record FROM cells WHERE nested_index=?", (int(index),)).fetchone()
                    if row:
                        for key, ids in json.loads(zlib.decompress(row[0]))["sourced_catalogue_context"].items():
                            if isinstance(ids, list):
                                evidence.setdefault(key, set()).update(ids)
                            elif isinstance(ids, dict):
                                evidence.setdefault(key, set()).update(ids)
                bound_concepts = {"CH": "chaos", "CM": "canyon", "FO": "graben",
                                  "LB": "canyon", "UN": "dunes"}
                for fid in evidence.get("gazetteer_approximate_bounds", ()):
                    feature = self.features["gazetteer"].get(fid)
                    cid = bound_concepts.get(feature["type_code"]) if feature else None
                    if cid in per_concept and "Approximate published bounds" not in per_concept[cid]["flags"]:
                        per_concept[cid]["flags"].append("Approximate published bounds")
                labels = [self.features["gazetteer"].get(fid) for fid in evidence.get("gazetteer", ())]
                labels = [x for x in labels if x and x.get("approval") == "Adopted by IAU"]
                label = max(labels, key=lambda x: (x.get("diameter_km") or 0, x["name"]))["name"] if labels else None
                count = self.pack["records"][cells].astype(np.uint32).sum(axis=0)
                areas.append({"tile": int(cells[0]) >> 4, "cells": [f"HPX128:{i}" for i in cells],
                    "best_cell": f"HPX128:{best}", "tier": tier,
                    "match_mean": int(values.mean()), "match_best": int(values.max()),
                    "concepts": per_concept,
                    "records": dict(zip(("ctx", "hirise", "dtm", "crism"), map(int, count))),
                    "method": "compatible" if request.method is None or bool(method_mask[cells].any()) else "not established",
                    "sparse": bool(sparse[cells].any()), "label": label,
                    "point_features": {k: sorted(v) for k, v in evidence.items() if k not in {"structures", "gazetteer_approximate_bounds"}},
                    "demo": any(x["status"] == "DEMO" for x in per_concept.values())})
        areas.sort(key=lambda a: (-a["match_mean"], -len(a["cells"]), int(a["cells"][0][7:])))
        for rank, area in enumerate(areas[:request.limit], 1):
            area["rank"] = rank
        base["areas"] = areas
        return base
