"""Offline tests: achievement steps on the 実績 page, the clock check against pota.app, trail / river parks."""
import os
import sys
import tempfile
import time
import unittest
from email.utils import formatdate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import mypota  # noqa: E402
import potacommon  # noqa: E402
import spots  # noqa: E402


class GoalsTest(unittest.TestCase):
    def test_unique_reference_levels(self):
        self.assertEqual([mypota.next_unique(n) for n in (0, 10, 74, 75, 950, 1000, 7999, 8000)],
                         [10, 20, 75, 100, 1000, 1500, 8000, None])

    def test_repeat_offender(self):
        self.assertEqual(mypota.goals(9), {"has": [], "next": None, "left": None})       # under halfway: no hint
        self.assertEqual(mypota.goals(12), {"has": [], "next": "Oasis", "left": 8})
        self.assertEqual(mypota.goals(41), {"has": ["Fox Den"], "next": "Bear Cave", "left": 19})
        self.assertEqual(mypota.goals(120)["has"], ["Oasis Tier 2"])
        self.assertEqual(mypota.goals(100)["next"], "Oasis Tier 2")
        self.assertEqual(mypota.goals(530), {"has": ["Eagle's Nest Tier 5"], "next": None, "left": None})

    def test_kilo(self):
        self.assertEqual(mypota.goals(400, kilo=True)["next"], None)
        self.assertEqual(mypota.goals(700, kilo=True), {"has": [], "next": "Kilo", "left": 300})
        self.assertEqual(mypota.goals(1000, kilo=True)["has"], ["Kilo"])

    def test_clock_skew(self):
        potacommon._note_clock(formatdate(time.time() - 300, usegmt=True))   # pota.app 5 min behind us
        self.assertAlmostEqual(potacommon.clock_skew(), 300, delta=2)
        potacommon._note_clock(formatdate(time.time() + 120, usegmt=True))
        self.assertAlmostEqual(potacommon.clock_skew(), -120, delta=2)
        potacommon._note_clock(formatdate(time.time() + 5, usegmt=True))
        self.assertIsNone(potacommon.clock_skew())                           # close enough
        potacommon._note_clock(None)                                         # no Date header: keep the last
        self.assertIsNone(potacommon.clock_skew())

    def test_linear_parks(self):
        # US-0197 Kern National Wild and Scenic River, US-2350 Prairie Spirit Trail State Trail, US-0001 Acadia NP
        self.assertEqual(spots.linear_parks(["US-0197", "US-2350", "US-0001", "XX-0000"]), ["US-0197", "US-2350"])


if __name__ == "__main__":
    unittest.main()
