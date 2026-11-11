"""Local topology in Mars-sphere gnomonic charts, with spherical measurement."""
from dataclasses import dataclass
import math

import numpy as np
from pyproj import Geod
from shapely import Geometry, GeometryCollection, LineString, Point, Polygon, box, union_all
from shapely.validation import explain_validity

from .contracts import MultiPolygon, QueryShape, Surface
from .grid import CANONICAL, RADIUS_M, normalize

GEOD = Geod(a=RADIUS_M, f=0)
FOOTPRINT_LIMIT_DEG = 25
QUERY_LIMIT_DEG = 35  # 35 + 2*25 < 90; overlapping caps stay inside the query chart.
CORRIDOR_LIMIT_DEG = 2
BUFFER_QUAD_SEGMENTS = 32
EMPTY = GeometryCollection()


def vectors(coordinates, crs=CANONICAL) -> np.ndarray:
    lon, lat = np.deg2rad(normalize(coordinates, crs)).T
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


@dataclass(frozen=True)
class Cap:
    center: np.ndarray
    chord: float

    @classmethod
    def enclosing(cls, vertices, limit_deg: float):
        mean = vertices.mean(axis=0)
        norm = np.linalg.norm(mean)
        if norm < 1e-12:
            raise ValueError("geometry cannot be represented in one bounded Mars chart")
        center = mean / norm
        chord = float(np.max(np.linalg.norm(vertices - center, axis=1))) + 1e-12
        if chord > 2 * math.sin(math.radians(limit_deg) / 2):
            raise ValueError(f"geometry exceeds {limit_deg}° chart radius; split into bounded pieces")
        return cls(center, chord)

    def intersects(self, other: "Cap") -> bool:
        # Chord distance obeys the triangle inequality. False positives are allowed.
        return bool(np.linalg.norm(self.center - other.center) <= self.chord + other.chord)

    def index_box(self):
        x, y = self.center[:2]
        return box(x - self.chord, y - self.chord, x + self.chord, y + self.chord)


class Chart:
    def __init__(self, center):
        self.center = center
        north_axis = (0, 0, 1) if abs(center[2]) < 0.9 else (1, 0, 0)
        east = np.cross(north_axis, center)
        east /= np.linalg.norm(east)
        self.basis = np.stack((east, np.cross(center, east)), axis=1)

    def project(self, xyz):
        depth = xyz @ self.center
        if np.any(depth <= 0):
            raise ValueError("geometry crosses the gnomonic horizon")
        return (xyz @ self.basis) * (RADIUS_M / depth[:, None])

    def geographic(self, xy):
        xyz = self.center + (np.asarray(xy) / RADIUS_M) @ self.basis.T
        lon = np.arctan2(xyz[:, 1], xyz[:, 0])
        lat = np.arctan2(xyz[:, 2], np.hypot(xyz[:, 0], xyz[:, 1]))
        return np.rad2deg(lon), np.rad2deg(lat)

    def area(self, shape: Geometry) -> float:
        if shape.geom_type == "Polygon" and not shape.is_empty:
            def ring_area(ring):
                return abs(GEOD.polygon_area_perimeter(*self.geographic(ring.coords))[0])
            return max(0.0, ring_area(shape.exterior) - math.fsum(map(ring_area, shape.interiors)))
        return math.fsum(self.area(part) for part in getattr(shape, "geoms", ()))

    def length(self, shape: Geometry) -> float:
        if shape.geom_type == "LineString" and not shape.is_empty:
            return GEOD.line_length(*self.geographic(shape.coords))
        return math.fsum(self.length(part) for part in getattr(shape, "geoms", ()))


@dataclass(frozen=True)
class Part:
    cap: Cap
    rings: tuple[np.ndarray, ...]

    def project(self, chart: Chart) -> Polygon:
        exterior, *holes = [chart.project(ring) for ring in self.rings]
        return Polygon(exterior, holes)


def _part(rings, crs, limit) -> Part:
    if not rings:
        raise ValueError("polygon has no exterior")
    converted = []
    for ring in rings:
        if len(ring) < 4:
            raise ValueError("ring needs at least four positions including closure")
        xyz = vectors(ring, crs)
        if np.linalg.norm(xyz[0] - xyz[-1]) > 1e-14:
            raise ValueError("ring is not closed")
        xyz[-1] = xyz[0]
        converted.append(xyz)
    cap = Cap.enclosing(np.concatenate([ring[:-1] for ring in converted]), limit)
    part = Part(cap, tuple(converted))
    shape = part.project(Chart(cap.center))
    if not shape.is_valid or shape.area <= 0:
        raise ValueError(explain_validity(shape) if not shape.is_valid else "polygon has no area")
    return part


def surface_parts(shape: Surface, crs=CANONICAL, limit=FOOTPRINT_LIMIT_DEG) -> tuple[Part, ...]:
    """Bounded components are independent support fragments and will be unioned."""
    if shape.type == "Global":
        return ()
    polygons = shape.coordinates if isinstance(shape, MultiPolygon) else (shape.coordinates,)
    if not polygons:
        raise ValueError("empty multipolygon")
    return tuple(_part(rings, crs, limit) for rings in polygons)


@dataclass(frozen=True)
class Window:
    cap: Cap
    chart: Chart
    shape: Geometry
    measure: str
    size: float
    route: tuple[tuple[LineString, float, float], ...] = ()

    @classmethod
    def from_geometry(cls, geometry: QueryShape, corridor_width_m=None):
        if geometry.type in {"Point", "LineString"}:
            is_point = geometry.type == "Point"
            positions = [geometry.coordinates] if is_point else geometry.coordinates
            if not is_point and len(positions) < 2:
                raise ValueError("route requires at least two positions")
            xyz = vectors(positions)
            cap = Cap.enclosing(xyz, QUERY_LIMIT_DEG)
            chart = Chart(cap.center)
            projected = chart.project(xyz)
            if is_point:
                return cls(cap, chart, Point(projected[0]), "point", 1.0)
            line = LineString(projected)
            if not line.is_simple or np.any(np.all(np.diff(projected, axis=0) == 0, axis=1)):
                raise ValueError("use a nondegenerate route segment without repeats or crossings")
            if corridor_width_m is None:
                segments = []
                chainage = 0.0
                for start, end in zip(projected, projected[1:]):
                    segment = LineString((start, end))
                    next_chainage = chainage + chart.length(segment)
                    segments.append((segment, chainage, next_chainage))
                    chainage = next_chainage
                domain = LineString(((0, 0), (chainage, 0)))
                return cls(cap, chart, domain, "length_m", chainage, tuple(segments))
            # The largest gnomonic stretch is sec²(c). Outward compensation also
            # covers GEOS's polygonal approximation of round joins and end caps.
            half_width = corridor_width_m / 2
            angle = 2 * math.asin(cap.chord / 2) + half_width / RADIUS_M
            if angle > math.radians(CORRIDOR_LIMIT_DEG):
                raise ValueError("split buffered routes into segments within a 2° chart radius")
            projected_width = half_width / (math.cos(angle)**2 * math.cos(math.pi / (2 * BUFFER_QUAD_SEGMENTS)))
            shape = line.buffer(projected_width, quad_segs=BUFFER_QUAD_SEGMENTS)
            if shape.is_empty:
                raise ValueError("corridor is too narrow to represent at floating-point precision")
            radius = math.atan(np.max(np.linalg.norm(np.asarray(shape.exterior.coords), axis=1)) / RADIUS_M)
            buffer_cap = Cap(cap.center, 2 * math.sin(radius / 2) + 1e-12)
            return cls(buffer_cap, chart, shape, "area_m2", chart.area(shape))

        parts = surface_parts(geometry, limit=QUERY_LIMIT_DEG)
        cap = Cap.enclosing(np.concatenate([part.rings[0][:-1] for part in parts]), QUERY_LIMIT_DEG)
        chart = Chart(cap.center)
        shape = union_all([part.project(chart) for part in parts])
        area = chart.area(shape)
        if area <= 0:
            raise ValueError("query polygon has no measurable spherical area")
        return cls(cap, chart, shape, "area_m2", area)

    def clip_part(self, part: Part) -> Geometry:
        if not self.cap.intersects(part.cap):
            return EMPTY
        polygon = part.project(self.chart)
        if self.route:
            return self._clip_route(polygon)
        return self.shape if polygon.covers(self.shape) else self.shape.intersection(polygon)

    def _clip_route(self, polygon: Polygon) -> Geometry:
        # Every clipped segment is converted to intervals on the same chainage
        # axis. Off-line roundoff in two GEOS intersections cannot inflate union length.
        intervals = []
        for segment, start, end in self.route:
            if polygon.covers(segment):
                intervals.append(LineString(((start, 0), (end, 0))))
                continue
            intersection = segment.intersection(polygon)
            pieces = getattr(intersection, "geoms", (intersection,))
            for piece in pieces:
                if piece.geom_type == "LineString" and not piece.is_empty:
                    endpoints = (piece.coords[0], piece.coords[-1])
                    offsets = [self._chainage(segment, point, start, end) for point in endpoints]
                    if offsets[0] != offsets[1]:
                        intervals.append(LineString(((offsets[0], 0), (offsets[1], 0))))
        return union_all(intervals)

    def _chainage(self, segment, point, start, end):
        first, last = segment.coords
        if point == first:
            return start
        if point == last:
            return end
        return min(end, start + GEOD.line_length(*self.chart.geographic([first, point])))

    def fraction(self, geometry: Geometry) -> float:
        if geometry.is_empty:
            return 0.0
        if geometry.covers(self.shape):
            return 1.0
        if self.measure == "point":
            return 0.0
        size = self.chart.area(geometry) if self.measure == "area_m2" else geometry.length
        return min(1.0, max(0.0, size / self.size))
