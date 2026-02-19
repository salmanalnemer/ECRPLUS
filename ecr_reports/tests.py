from __future__ import annotations

from django.test import TestCase

from ecr_reports.utils.geo import Point, point_in_polygon


class GeoUtilsTests(TestCase):
    def test_point_in_polygon_square(self):
        square = [
            (24.0, 46.0),
            (24.0, 47.0),
            (25.0, 47.0),
            (25.0, 46.0),
        ]
        self.assertTrue(point_in_polygon(Point(24.5, 46.5), square))
        self.assertFalse(point_in_polygon(Point(26.0, 46.5), square))
