"""Park references in a spot comment: only POTA prefixes, so a radio's model ("IC-7300") is not a park."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import spots  # noqa: E402


class CommentParks(unittest.TestCase):
    def test_radio_models_are_not_parks(self):
        spot = {"reference": "US-1359", "comments": "IC-7300 5W EFHW, 2fer US-8847, FT-891 backup"}
        self.assertEqual(spots.parks_of(spot), ["US-1359", "US-8847"])

    def test_hunters_respot_names_the_hunters_park(self):
        spot = {"activator": "JA1ABC/P", "reference": "JP-1138", "spotter": "JH1XYZ", "comments": "P2P from JP-1234"}
        self.assertEqual(spots.parks_of(spot), ["JP-1138"])
        own = dict(spot, spotter="JA1ABC", comments="also JP-1234")
        self.assertEqual(spots.parks_of(own), ["JP-1138", "JP-1234"])
        fer = dict(spot, comments="2fer w/ JP-1234")
        self.assertEqual(spots.parks_of(fer), ["JP-1138", "JP-1234"])

    def test_park_references_are_kept(self):
        self.assertEqual(spots.comment_parks("2fer JP-0157 / 3fer JP-1206"), ["JP-0157", "JP-1206"])
        self.assertEqual(spots.comment_parks("TS-590 and KX-2"), [])


if __name__ == "__main__":
    unittest.main()
