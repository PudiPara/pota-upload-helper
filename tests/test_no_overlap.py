"""Parks with no prefecture/state in common can't overlap: common_locations says "none" (the start refuses)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import spots  # noqa: E402


class NoOverlap(unittest.TestCase):
    def setUp(self):
        self.orig = spots.park_comments, spots._park_record
        spots.park_comments = lambda ref: ""          # offline: no pota.app comment or park record
        spots._park_record = lambda ref: {}

    def tearDown(self):
        spots.park_comments, spots._park_record = self.orig

    def test_other_country(self):
        r = spots.common_locations(["JP-1206", "US-1409"])     # JP-TK and US-PA
        self.assertEqual(r["options"], [])
        self.assertTrue(r["none"])

    def test_same_prefecture(self):
        r = spots.common_locations(["JP-1281", "JP-1206"])     # both JP-TK: may overlap, not proven either way
        self.assertEqual([o["code"] for o in r["options"]], ["JP-TK"])
        self.assertFalse(r["none"])

    def test_one_park_or_unknown(self):
        self.assertFalse(spots.common_locations(["JP-1206"])["none"])
        self.assertFalse(spots.common_locations(["JP-1206", "XX-99999"])["none"])   # unknown: no constraint


if __name__ == "__main__":
    unittest.main()
