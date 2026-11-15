"""Subsystem 09 · Terrain routing.

Boxes:
  * Shared mobility contract  - tagged per-edge results from Subsystem 04
  * Directed terrain graph    - CSR, 4 or 8 neighbours, no corner cutting
  * Recompute outbound and return - two directed Dijkstra runs per request:
        forward graph from the crew   -> time(crew -> every cell)
        transposed graph from shelter -> time(every cell -> shelter)
  * Route reconstruction      - forward geometry from parent pointers; the
        return run's pointers already point toward the shelter
  * Diverse candidate routes  - directed baseline + bounded, spatially distinct alternates

Closures are applied per request without mutating the baseline graph.

Dijkstra backend: SciPy's csgraph Dijkstra when SciPy is importable,
otherwise an equivalent pure-Python Dijkstra over the same CSR arrays.
Times are identical; with exact ties the two may pick different but equally
fast cells. The backend in use is reported with every plan.
"""
from collections import OrderedDict, deque
from copy import copy
from dataclasses import dataclass, replace
from heapq import heappop, heappush
from math import inf

import numpy as np

from .errors import (LEG_ENDPOINT_EXCLUDED, LEG_NO_EVIDENCE, LEG_SEARCH_LIMIT, LEG_NO_PATH, LEG_OK, LEG_OUT_OF_BOUNDS,
                     MarswalkError)
from .mobility import TAG_UNSUPPORTED, EdgeTimes, human_traversal_time, pace_for

try:  # optional accelerator
    from scipy.sparse import csr_matrix as _scipy_csr
    from scipy.sparse.csgraph import dijkstra as _scipy_dijkstra
except ImportError:  # pragma: no cover - exercised in environments without SciPy
    _scipy_csr = _scipy_dijkstra = None

NEIGHBOURS_4 = ((-1, 0), (0, -1), (0, 1), (1, 0))
NEIGHBOURS_8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
NO_PARENT = -9999


def available_backends():
    return ("scipy", "python") if _scipy_dijkstra is not None else ("python",)


# ------------------------------------------------------------------ CSR helpers
@dataclass(frozen=True)
class CSR:
    indptr: np.ndarray
    indices: np.ndarray
    data: np.ndarray
    edge_ids: np.ndarray       # data position -> edge id in the TerrainGraph
    n: int

    def transposed(self):
        src = np.repeat(np.arange(self.n), np.diff(self.indptr))
        return csr_from_edges(self.indices, src, self.data, self.edge_ids, self.n)

    def with_data(self, data):
        return CSR(self.indptr, self.indices, data, self.edge_ids, self.n)

    def without_closed_edges(self, blocked):
        keep = ~blocked[self.edge_ids]
        offsets = np.empty(len(keep) + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(keep, out=offsets[1:])
        return CSR(offsets[self.indptr], self.indices[keep], self.data[keep], self.edge_ids[keep], self.n)


def csr_from_edges(src, dst, data, edge_ids, n):
    order = np.lexsort((dst, src))
    s, d = np.asarray(src)[order], np.asarray(dst)[order]
    key = s.astype(np.int64) * n + d
    if key.size > 1 and np.any(key[1:] == key[:-1]):
        raise MarswalkError("INVALID_GRAPH", "duplicate edge")
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.bincount(s, minlength=n), out=indptr[1:])
    return CSR(indptr, d.astype(np.int64), np.asarray(data, float)[order], np.asarray(edge_ids)[order], n)


def _dijkstra_python(csr, source, limit):
    ip, ix, dd = csr.indptr.tolist(), csr.indices.tolist(), csr.data.tolist()
    dist = [inf] * csr.n
    pred = [NO_PARENT] * csr.n
    dist[source] = 0.0
    heap = [(0.0, source)]
    while heap:
        d, u = heappop(heap)
        if d > dist[u]:
            continue
        for p in range(ip[u], ip[u + 1]):
            v = ix[p]
            nd = d + dd[p]
            if nd < dist[v] and nd <= limit:
                dist[v] = nd
                pred[v] = u
                heappush(heap, (nd, v))
    return np.asarray(dist, float), np.asarray(pred, np.int64)


def dijkstra(csr, source, *, limit=inf, backend="auto"):
    """Single-source minimum weights and parent pointers over a CSR graph."""
    if backend == "auto":
        backend = "scipy" if _scipy_dijkstra is not None else "python"
    if backend == "scipy":
        if _scipy_dijkstra is None:
            raise MarswalkError("BACKEND_UNAVAILABLE", "SciPy is not installed")
        mat = _scipy_csr((csr.data, csr.indices, csr.indptr), shape=(csr.n, csr.n))
        dist, pred = _scipy_dijkstra(mat, directed=True, indices=int(source),
                                     return_predecessors=True, limit=limit)
        return dist, pred.astype(np.int64)
    if backend == "python":
        return _dijkstra_python(csr, int(source), limit)
    raise MarswalkError("BACKEND_UNAVAILABLE", backend)


# ------------------------------------------------------------------ directed terrain graph
def grid_moves(passable, dx, dy, neighbours):
    """Candidate moves between passable cells, with the no-corner-cutting rule."""
    rows, cols = passable.shape
    idx = np.arange(rows * cols, dtype=np.int64).reshape(rows, cols)
    parts = {k: [] for k in ("src", "dst", "side_a", "side_b", "length")}
    for dr, dc in neighbours:
        r0, r1 = max(0, -dr), rows - max(0, dr)
        c0, c1 = max(0, -dc), cols - max(0, dc)
        if r1 <= r0 or c1 <= c0:
            continue
        S = (slice(r0, r1), slice(c0, c1))
        D = (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))
        ok = passable[S] & passable[D]
        if dr and dc:
            A = (slice(r0 + dr, r1 + dr), slice(c0, c1))
            B = (slice(r0, r1), slice(c0 + dc, c1 + dc))
            ok &= passable[A] & passable[B]
            sa, sb = idx[A][ok], idx[B][ok]
        else:
            sa = sb = np.full(int(ok.sum()), -1, dtype=np.int64)
        parts["src"].append(idx[S][ok])
        parts["dst"].append(idx[D][ok])
        parts["side_a"].append(sa)
        parts["side_b"].append(sb)
        parts["length"].append(np.full(int(ok.sum()), float(np.hypot(dr * dy, dc * dx))))
    return {k: np.concatenate(v) if v else np.zeros(0) for k, v in parts.items()}


class TerrainGraph:
    """Baseline directed graph for one (baseline inputs, pace, scenario, neighbourhood).
    Built once; never modified by requests."""

    def __init__(self, baseline, pace, *, scenario="nominal", neighbours=8):
        if neighbours not in (4, 8):
            raise MarswalkError("INVALID_PROFILE", "neighbours must be 4 or 8")
        self.baseline = baseline
        self.neighbours = neighbours
        self.mobility = pace
        sup = baseline.support
        moves = grid_moves(np.asarray(baseline.routable), sup.cell_dx_m, sup.cell_dy_m,
                           NEIGHBOURS_8 if neighbours == 8 else NEIGHBOURS_4)
        self.src = moves["src"].astype(np.int64)
        self.dst = moves["dst"].astype(np.int64)
        self.side_a = moves["side_a"].astype(np.int64)
        self.side_b = moves["side_b"].astype(np.int64)
        self.length_m = moves["length"].astype(float)
        z = np.asarray(baseline.z_m, float).ravel()
        self.dz_m = z[self.dst] - z[self.src] if self.src.size else np.zeros(0)
        if not self.src.size:
            self.times = EdgeTimes(np.zeros(0), np.zeros(0, np.uint8), pace.name, (),
                                   np.zeros(0) if hasattr(pace, "edge_times") else None)
        elif hasattr(pace, "edge_times"):        # vehicle model (Subsystem 05)
            self.times = pace.edge_times(self.length_m, self.dz_m, self.src, self.dst, baseline)
        else:                                    # human pace model (Subsystem 04)
            self.times = human_traversal_time(self.length_m, self.dz_m, model=pace, scenario=scenario)
        self.n = int(np.prod(sup.shape))

    def __len__(self):
        return int(self.src.size)


# ------------------------------------------------------------------ legs
@dataclass(frozen=True)
class Leg:
    status: str
    start: tuple
    goal: tuple
    reason: str = ""
    cells: tuple = ()
    seconds: float | None = None
    length_m: float | None = None
    surface_m: float | None = None
    ascent_m: float | None = None
    descent_m: float | None = None
    max_abs_grade: float | None = None
    max_slope_deg: float | None = None
    edge_ids: tuple = ()
    energy_j: float | None = None

    @property
    def ok(self):
        return self.status == LEG_OK

    def to_dict(self):
        out = {k: getattr(self, k) for k in ("status", "reason", "seconds", "length_m", "surface_m",
                                             "ascent_m", "descent_m", "max_abs_grade", "max_slope_deg", "energy_j")}
        out.update(start=list(self.start), goal=list(self.goal), cells=[list(c) for c in self.cells])
        return out


# ------------------------------------------------------------------ request router
class Router:
    """One request: baseline graph minus closures. Caches Dijkstra fields."""

    def __init__(self, graph, closure_cells=(), *, backend="auto", limit_s=inf, outbound_limit_s=None, indexed=None):
        self.graph = graph
        self.baseline = graph.baseline
        shape = self.baseline.support.shape
        self.shape = shape
        closed = np.zeros(shape, bool)
        for r, c in closure_cells:
            if not (0 <= r < shape[0] and 0 <= c < shape[1]):
                raise MarswalkError("BAD_POSITION", f"closure cell {[r, c]} outside the grid")
            closed[r, c] = True
        self.closed = closed
        cf = closed.ravel()
        bad = cf[graph.src] | cf[graph.dst]
        diag = graph.side_a >= 0
        bad[diag] |= cf[graph.side_a[diag]] | cf[graph.side_b[diag]]
        if indexed is None:
            keep = np.isfinite(graph.times.seconds) & ~bad
            self.edge_ids = np.flatnonzero(keep)
            self._unknown_edges = np.flatnonzero(~bad & (graph.times.tag == TAG_UNSUPPORTED))
            self.csr = csr_from_edges(graph.src[keep], graph.dst[keep], graph.times.seconds[keep],
                                      self.edge_ids, graph.n)
            self.csr_t = self.csr.transposed()
            self._key = graph.src[self.edge_ids] * graph.n + graph.dst[self.edge_ids]
            order = np.argsort(self._key)
            self._key, self._key_edges = self._key[order], self.edge_ids[order]
        else:
            self.edge_ids = indexed.edge_ids[~bad[indexed.edge_ids]]
            self._unknown_edges = indexed._unknown_edges[~bad[indexed._unknown_edges]]
            self.csr = indexed.csr.without_closed_edges(bad)
            self.csr_t = indexed.csr_t.without_closed_edges(bad)
            open_keys = ~bad[indexed._key_edges]
            self._key, self._key_edges = indexed._key[open_keys], indexed._key_edges[open_keys]
        self.backend = backend if backend != "auto" else ("scipy" if "scipy" in available_backends() else "python")
        self.limit_s = limit_s
        # Search horizon for outbound fields only. The home field stays exact so
        # the direct-return gate can tell "over reserve" from "no route".
        self.outbound_limit_s = limit_s if outbound_limit_s is None else min(limit_s, outbound_limit_s)
        self._fwd, self._bwd, self._energy_fields = {}, {}, {}
        self._distance_fields = {}
        self._last_forward_field = {}
        self.dijkstra_runs = 0

    def for_request(self, outbound_limit_s=None):
        """Share topology and bounded shelter fields, with fresh request diagnostics."""
        router = copy(self)
        router._fwd, router._energy_fields = {}, {}
        router.outbound_limit_s = self.limit_s if outbound_limit_s is None else min(self.limit_s, outbound_limit_s)
        router.dijkstra_runs = 0
        return router

    # -- helpers
    def node(self, cell):
        return int(cell[0]) * self.shape[1] + int(cell[1])

    def cell(self, node):
        return divmod(int(node), self.shape[1])

    def edge_lookup(self, a, b):
        q = np.asarray(a, np.int64) * self.graph.n + np.asarray(b, np.int64)
        pos = np.searchsorted(self._key, q)
        if np.any(pos >= self._key.size) or np.any(self._key[np.minimum(pos, self._key.size - 1)] != q):
            raise MarswalkError("INVALID_GRAPH", "route uses an edge missing from the request graph")
        return self._key_edges[pos]

    # -- the two runs
    def outbound_field(self, start):
        s = self.node(start)
        if s not in self._fwd:
            key = (s, self.outbound_limit_s)
            if key not in self._last_forward_field:
                self._last_forward_field.clear()
                self._last_forward_field[key] = dijkstra(self.csr, s, limit=self.outbound_limit_s, backend=self.backend)
                self.dijkstra_runs += 1
            self._fwd[s] = self._last_forward_field[key]
        return self._fwd[s]

    def return_field(self, home):
        h = self.node(home)
        if h not in self._bwd:
            self._bwd.clear()
            self._bwd[h] = dijkstra(self.csr_t, h, limit=self.limit_s, backend=self.backend)
            self.dijkstra_runs += 1
        return self._bwd[h]

    def time_to_home(self, home):
        dist, _ = self.return_field(home)
        return dist.reshape(self.shape)

    # -- legs
    def leg_outbound(self, start, goal):
        refused = self._endpoints(start, goal)
        if refused:
            return refused
        dist, pred = self.outbound_field(start)
        s, g = self.node(start), self.node(goal)
        if not np.isfinite(dist[g]):
            if self.outbound_limit_s < self.limit_s:
                return Leg(LEG_SEARCH_LIMIT, tuple(start), tuple(goal),
                           f"no supported path found within the {self.outbound_limit_s:g} s outbound search horizon")
            return self._diagnose(start, goal)
        nodes = [g]
        while nodes[-1] != s:
            nodes.append(int(pred[nodes[-1]]))
        return self._leg(start, goal, nodes[::-1])

    def leg_return(self, start, home):
        refused = self._endpoints(start, home)
        if refused:
            return refused
        dist, pred = self.return_field(home)
        s, h = self.node(start), self.node(home)
        if not np.isfinite(dist[s]):
            return self._diagnose(start, home)
        nodes = [s]
        while nodes[-1] != h:
            nodes.append(int(pred[nodes[-1]]))      # next hop toward the shelter
        return self._leg(start, home, nodes)

    def shortest_distance(self, start, goal):
        """Shortest horizontal distance on this graph, before resource checks."""
        refused = self._endpoints(start, goal)
        if refused:
            return refused
        s, g = self.node(start), self.node(goal)
        if g not in self._distance_fields:
            self._distance_fields.clear()
            weights = self.csr_t.with_data(self.graph.length_m[self.csr_t.edge_ids])
            self._distance_fields[g] = dijkstra(weights, g, backend=self.backend)
            self.dijkstra_runs += 1
        distance, parent = self._distance_fields[g]
        if not np.isfinite(distance[s]):
            return self._diagnose(start, goal)
        nodes = [s]
        while nodes[-1] != g:
            nodes.append(int(parent[nodes[-1]]))
        return self._leg(start, goal, nodes)

    def energy_alternatives(self, leg, max_discharge_w):
        """Fastest power-admissible, minimum energy and two mixed-weight paths."""
        if not leg.ok or not leg.edge_ids:
            return ()
        g = self.graph
        edges = self.csr.edge_ids
        seconds, joules = g.times.seconds[edges], g.times.energy_j[edges]
        admissible = joules <= max_discharge_w * seconds
        if not np.any(admissible):
            return ()
        start, goal = self.node(leg.start), self.node(leg.goal)
        energy_scale = max(1.0, max_discharge_w)
        seen, alternatives = {leg.edge_ids}, []
        for time_weight, energy_weight in ((1, 0), (0, 1), (1, 1), (1, 4)):
            key = (start, max_discharge_w, time_weight, energy_weight)
            if key not in self._energy_fields:
                weight = time_weight * seconds + energy_weight * (joules / energy_scale)
                csr = self.csr.with_data(np.where(admissible, weight, np.inf))
                self._energy_fields[key] = dijkstra(csr, start, backend=self.backend)
                self.dijkstra_runs += 1
            dist, pred = self._energy_fields[key]
            if np.isfinite(dist[goal]):
                nodes = [goal]
                while nodes[-1] != start:
                    nodes.append(int(pred[nodes[-1]]))
                candidate = self._leg(leg.start, leg.goal, nodes[::-1])
                if candidate.edge_ids not in seen:
                    seen.add(candidate.edge_ids)
                    alternatives.append(candidate)
        return tuple(alternatives)

    def climb_alternatives(self, leg):
        """Generate candidates from shared, dimensioned climb penalties [s/m]."""
        if not leg.ok or not leg.edge_ids:
            return ()
        ascent = np.maximum(self.graph.dz_m[self.csr.edge_ids], 0)
        seen, alternatives = {leg.edge_ids}, []
        start, goal = self.node(leg.start), self.node(leg.goal)
        for climb_s_per_m in (10.0, 60.0):
            key = (start, "climb", climb_s_per_m)
            if key not in self._energy_fields:
                weights = self.csr.data + climb_s_per_m * ascent
                self._energy_fields[key] = dijkstra(self.csr.with_data(weights), start, backend=self.backend)
                self.dijkstra_runs += 1
            dist, parent = self._energy_fields[key]
            if np.isfinite(dist[goal]):
                nodes = [goal]
                while nodes[-1] != start:
                    nodes.append(int(parent[nodes[-1]]))
                candidate = self._leg(leg.start, leg.goal, nodes[::-1])
                if candidate.edge_ids not in seen:
                    seen.add(candidate.edge_ids)
                    alternatives.append(candidate)
        return tuple(alternatives)

    def _endpoints(self, a, b):
        a, b = tuple(map(int, a)), tuple(map(int, b))
        rows, cols = self.shape
        for c in (a, b):
            if not (0 <= c[0] < rows and 0 <= c[1] < cols):
                return Leg(LEG_OUT_OF_BOUNDS, a, b, f"cell {list(c)} is outside the grid")
        for c in (a, b):
            if self.baseline.known_excluded[c] or self.closed[c]:
                why = "closed by a field report" if self.closed[c] else "excluded by traversability"
                return Leg(LEG_ENDPOINT_EXCLUDED, a, b, f"cell {list(c)} is {why}")
        for c in (a, b):
            if self.baseline.unknown[c]:
                return Leg(LEG_NO_EVIDENCE, a, b, f"cell {list(c)} has insufficient terrain evidence")
        return None

    def _diagnose(self, a, b):
        """Relax unknown cells and mobility edges while preserving known
        exclusions and closures. The diagnostic connection is never drawn."""
        a, b = tuple(map(int, a)), tuple(map(int, b))
        relaxed = (np.asarray(self.baseline.routable) | np.asarray(self.baseline.unknown)) & ~self.closed
        unknown = np.asarray(self.baseline.unknown)
        diagnostic_edges = np.concatenate((self.edge_ids, self._unknown_edges))
        allowed = set(zip(self.graph.src[diagnostic_edges], self.graph.dst[diagnostic_edges]))
        moves = NEIGHBOURS_8 if self.graph.neighbours == 8 else NEIGHBOURS_4
        rows, cols = self.shape
        seen, queue = {a}, deque([a])
        while queue:
            r, c = queue.popleft()
            if (r, c) == b:
                return Leg(LEG_NO_EVIDENCE, a, b, "a connection would require unverified terrain; no route is drawn")
            for dr, dc in moves:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols) or (nr, nc) in seen or not relaxed[nr, nc]:
                    continue
                if dr and dc and not (relaxed[r + dr, c] and relaxed[r, c + dc]):
                    continue
                touches_unknown = unknown[r, c] or unknown[nr, nc] or (dr and dc and (unknown[r + dr, c] or unknown[r, c + dc]))
                if not touches_unknown and (self.node((r, c)), self.node((nr, nc))) not in allowed:
                    continue
                seen.add((nr, nc))
                queue.append((nr, nc))
        suffix = "" if self.limit_s == inf else f" within the {self.limit_s:.0f} s search horizon"
        return Leg(LEG_NO_PATH, a, b, "no admissible connection in the modelled area" + suffix)

    def _leg(self, a, b, nodes):
        nodes = np.asarray(nodes, np.int64)
        rows, cols = np.divmod(nodes, self.shape[1])
        cells = tuple(zip(rows.tolist(), cols.tolist()))
        slope = np.asarray(self.baseline.slope_deg)[rows, cols]
        max_slope = float(np.nanmax(slope)) if np.isfinite(slope).any() else None
        if nodes.size == 1:
            return Leg(LEG_OK, tuple(a), tuple(b), "start equals goal", cells, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, max_slope, (),
                       None if self.graph.times.energy_j is None else 0.0)
        eids = self.edge_lookup(nodes[:-1], nodes[1:])
        g = self.graph
        length, dz = g.length_m[eids], g.dz_m[eids]
        return Leg(LEG_OK, tuple(a), tuple(b), "", cells,
                   seconds=float(g.times.seconds[eids].sum()), length_m=float(length.sum()),
                   surface_m=float(np.hypot(length, dz).sum()), ascent_m=float(dz[dz > 0].sum()),
                   descent_m=float(-dz[dz < 0].sum()), max_abs_grade=float(np.abs(dz / length).max()),
                   max_slope_deg=max_slope, edge_ids=tuple(eids.tolist()),
                   energy_j=None if g.times.energy_j is None else float(g.times.energy_j[eids].sum()))


class SearchCache:
    """Bounded caches owned by one serial planning session and terrain baseline."""

    def __init__(self, baseline):
        self.baseline = baseline
        self.graphs, self.topologies = OrderedDict(), OrderedDict()
        self.capacity = 6 if baseline.z_m.size < 250_000 else 2

    def router(self, profile, closures, *, backend="auto", outbound_limit_s=None):
        if backend == "auto":
            backend = available_backends()[0]
        # Live charge affects the ledger, while edge time and gross use depend
        # on the otherwise identical operating profile.
        if profile.platform == "rover":
            profile = replace(profile, initial_charge_j=profile.battery_capacity_j)
        if profile not in self.graphs:
            if len(self.graphs) >= 3:
                old, _ = self.graphs.popitem(last=False)
                self.topologies = OrderedDict((key, item) for key, item in self.topologies.items() if key[0] != old)
            graph = TerrainGraph(self.baseline, pace_for(profile), scenario=getattr(profile, "pace_scenario", "nominal"),
                                 neighbours=profile.neighbours)
            self.graphs[profile] = Router(graph, backend=backend)
        self.graphs.move_to_end(profile)
        key = profile, frozenset(closures), backend
        indexed = self.graphs[profile]
        if not key[1] and backend == indexed.backend:
            return indexed.for_request(outbound_limit_s)
        if key not in self.topologies:
            if len(self.topologies) >= self.capacity:
                self.topologies.popitem(last=False)
            self.topologies[key] = Router(indexed.graph, key[1], backend=backend, indexed=indexed)
        self.topologies.move_to_end(key)
        return self.topologies[key].for_request(outbound_limit_s)


# ------------------------------------------------------------------ diverse candidates
@dataclass(frozen=True)
class RouteAlternative:
    rank: int
    label: str
    leg: Leg
    stretch: float
    max_overlap: float


def _corridor(shape, cells, buffer_cells):
    mask = np.zeros(shape, bool)
    for r, c in cells:
        mask[r, c] = True
    for _ in range(buffer_cells):
        p = np.pad(mask, 1)
        grown = mask.copy()
        for dr in (0, 1, 2):
            for dc in (0, 1, 2):
                grown |= p[dr:dr + shape[0], dc:dc + shape[1]]
        mask = grown
    return mask.ravel()


def diverse_routes(router, start, goal, *, k=3, max_stretch=1.25, max_overlap=0.7,
                   penalty=1.6, max_iter=12, buffer_m=10.0):
    """Directed baseline plus up to k-1 alternates within `max_stretch` of the
    baseline time and with at most `max_overlap` of their time inside a
    `buffer_m` corridor around any accepted route. True times are always
    reported; penalties only steer the search."""
    if k < 1 or max_stretch < 1 or not 0 <= max_overlap <= 1 or penalty <= 1:
        raise MarswalkError("INVALID_REQUEST", "invalid candidate parameters")
    base = router.leg_outbound(start, goal)
    if not base.ok:
        return [RouteAlternative(0, "baseline", base, float("nan"), 0.0)]
    accepted = [RouteAlternative(0, "baseline", base, 1.0, 0.0)]
    if not base.seconds:
        return accepted
    sup = router.baseline.support
    buf = max(0, int(round(buffer_m / min(sup.cell_dx_m, sup.cell_dy_m))))
    corridors = [_corridor(router.shape, base.cells, buf)]
    true_t = router.graph.times.seconds
    mult = np.ones(true_t.size)
    mult[list(base.edge_ids)] *= penalty
    s, g = router.node(start), router.node(goal)
    for _ in range(max_iter):
        if len(accepted) >= k:
            break
        dist, pred = dijkstra(router.csr.with_data(router.csr.data * mult[router.csr.edge_ids]), s,
                              limit=inf, backend=router.backend)
        router.dijkstra_runs += 1
        if not np.isfinite(dist[g]):
            break
        nodes = [g]
        while nodes[-1] != s:
            nodes.append(int(pred[nodes[-1]]))
        leg = router._leg(start, goal, nodes[::-1])
        stretch = leg.seconds / base.seconds
        if stretch > max_stretch:
            break
        eids = np.asarray(leg.edge_ids)
        dst_nodes = router.graph.dst[eids]
        tot = true_t[eids].sum()
        overlap = max(float(true_t[eids][cor[dst_nodes]].sum() / tot) for cor in corridors)
        if overlap <= max_overlap:
            accepted.append(RouteAlternative(len(accepted), f"alternate_{len(accepted)}", leg, float(stretch), overlap))
            corridors.append(_corridor(router.shape, leg.cells, buf))
        mult[eids] *= penalty
    return accepted
