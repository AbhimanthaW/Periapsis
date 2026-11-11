from dataclasses import replace
import math
import unittest

from affine import Affine

from return_window_pipeline.coordinates import convert_latitude, normalize_longitude, normalize_position, pixel_center, transform_points, validate_crs
from return_window_pipeline.errors import CoordinateError
from return_window_pipeline.models import MarsReference

SPHERE = MarsReference("Mars", 3396000, 3396000, "planetocentric", "east", "0_360", "IAU2000_MARS", "m", "Test reference")
GEOGRAPHIC = "+proj=longlat +R=3396000 +type=crs"
EQC = "+proj=eqc +lat_ts=0 +lon_0=180 +R=3396000 +units=m +type=crs"


class CoordinateTests(unittest.TestCase):
    def test_seam_and_multiple_revolutions(self):
        for value, expected in [(0, 0), (180, -180), (360, 0), (-180, -180), (540, -180), (-540, -180), (359.75, -0.25)]:
            with self.subTest(value=value):
                self.assertEqual(normalize_longitude(value), expected)

    def test_west_positive_is_converted(self):
        self.assertEqual(normalize_longitude(15, "west"), -15)
        self.assertEqual(normalize_longitude(15, "west", "0_360"), 345)

    def test_longitude_rejects_nonfinite_and_unknown_convention(self):
        for value in [math.inf, -math.inf, math.nan]:
            with self.assertRaises(CoordinateError):
                normalize_longitude(value)
        with self.assertRaises(CoordinateError):
            normalize_longitude(1, "north")

    def test_spherical_latitudes_are_identical(self):
        for lat in [-90, -45, 0, 45, 90]:
            self.assertAlmostEqual(convert_latitude(lat, "planetographic", "planetocentric", SPHERE), lat)

    def test_oblate_latitude_matches_independent_cartesian_geometry(self):
        ref = replace(SPHERE, semi_major_m=3396190, semi_minor_m=3376200)
        # A point on an oblate ellipsoid with a 45-degree surface normal.
        a, b, normal = ref.semi_major_m, ref.semi_minor_m, math.pi / 4
        denominator = math.sqrt((a * math.cos(normal)) ** 2 + (b * math.sin(normal)) ** 2)
        x, z = a * a * math.cos(normal) / denominator, b * b * math.sin(normal) / denominator
        expected = math.degrees(math.atan2(z, x))
        converted = convert_latitude(45, "planetographic", "planetocentric", ref)
        self.assertAlmostEqual(converted, expected, places=11)
        self.assertAlmostEqual(convert_latitude(converted, "planetocentric", "planetographic", ref), 45, places=11)

    def test_latitude_rejects_out_of_domain(self):
        for lat in [-91, 91, math.nan]:
            with self.assertRaises(CoordinateError):
                convert_latitude(lat, "planetocentric", "planetographic", SPHERE)

    def test_normalized_position_declares_both_conversions(self):
        ref = replace(SPHERE, longitude_direction="west", latitude_type="planetographic", semi_minor_m=3376200)
        lon, lat = normalize_position(10, 45, ref)
        self.assertEqual(lon, -10)
        self.assertLess(lat, 45)

    def test_earth_crs_is_rejected(self):
        with self.assertRaises(CoordinateError):
            validate_crs("EPSG:4326", SPHERE)

    def test_analysis_grid_requires_metres(self):
        validate_crs(EQC, SPHERE, require_metric=True)
        for crs in [GEOGRAPHIC, "+proj=eqc +R=3396000 +units=km +type=crs"]:
            with self.assertRaises(CoordinateError):
                validate_crs(crs, SPHERE, require_metric=True)

    def test_projection_matches_analytical_equatorial_distance(self):
        points = transform_points(GEOGRAPHIC, EQC, [(180, 0), (181, 0)], SPHERE)
        self.assertAlmostEqual(points[0][0], 0, places=7)
        self.assertAlmostEqual(points[1][0], SPHERE.semi_major_m * math.pi / 180, places=7)
        self.assertAlmostEqual(points[1][1], 0, places=7)

    def test_projection_inverse_and_polar_case(self):
        stereo = "+proj=stere +lat_0=90 +lon_0=0 +R=3396000 +units=m +type=crs"
        projected = transform_points(GEOGRAPHIC, stereo, [(15, 85), (0, 90)], SPHERE)
        self.assertAlmostEqual(projected[1][0], 0, places=7)
        self.assertAlmostEqual(projected[1][1], 0, places=7)
        restored = transform_points(stereo, GEOGRAPHIC, projected[:1], SPHERE)[0]
        self.assertAlmostEqual(restored[0], 15, places=9)
        self.assertAlmostEqual(restored[1], 85, places=9)

    def test_non_spherical_centric_transform_requires_explicit_operation(self):
        ref = replace(SPHERE, semi_minor_m=3376200)
        source = "+proj=longlat +a=3396000 +b=3376200 +type=crs"
        with self.assertRaises(CoordinateError):
            transform_points(source, source, [(0, 45)], ref)

    def test_pixel_centres_use_column_row_and_half_cell(self):
        self.assertEqual(pixel_center(Affine(10, 0, 100, 0, -10, 200), 1, 2), (125.0, 185.0))
        with self.assertRaises(CoordinateError):
            pixel_center(Affine.identity(), -1, 0)

    def test_rotated_grid_pixel_centres(self):
        self.assertEqual(pixel_center(Affine(10, 2, 100, 3, -10, 200), 0, 0), (106.0, 196.5))
