"""P2P distances: great-circle km between the middle of my parks and the middle of theirs (spots.distance_km)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import spots  # noqa: E402


class Distance(unittest.TestCase):
    def test_great_circle(self):
        tokyo, osaka = (35.6812, 139.7671), (34.7025, 135.4959)      # the two main stations
        self.assertAlmostEqual(spots.great_circle_km(tokyo, osaka), 403, delta=2)
        self.assertEqual(spots.great_circle_km(tokyo, tokyo), 0)

    def test_middle(self):
        la, lo = spots.middle([(0, 0), (0, 10)])
        self.assertAlmostEqual(la, 0, places=6)
        self.assertAlmostEqual(lo, 5, places=6)
        la, lo = spots.middle([(0, 179), (0, -179)])                 # across the 180th meridian, not at 0
        self.assertAlmostEqual(abs(lo), 180, places=6)
        self.assertIsNone(spots.middle([]))

    def test_parks(self):
        a, b = spots.park_at("JP-1281"), spots.park_at("JP-1206")
        self.assertTrue(a and b)
        self.assertAlmostEqual(spots.distance_km(["JP-1281"], ["JP-1206"]), spots.great_circle_km(a, b), delta=0.1)
        # a 2fer is measured from the point between its parks
        mid = spots.middle([a, b])
        us = spots.park_at("US-11782")
        self.assertAlmostEqual(spots.distance_km(["JP-1281", "JP-1206"], ["US-11782"]), spots.great_circle_km(mid, us), delta=0.1)
        self.assertGreater(spots.distance_km(["JP-1281"], ["US-11782"]), 8000)

    def test_unknown_park(self):
        self.assertIsNone(spots.distance_km(["JP-1281"], ["XX-99999"]))
        self.assertIsNone(spots.distance_km([], ["JP-1281"]))


if __name__ == "__main__":
    unittest.main()
