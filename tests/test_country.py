import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import i18n
import spots


class CountryTest(unittest.TestCase):
    def test_example_parks(self):
        self.assertEqual(spots.example_parks("DE")["cc"], "DE")
        self.assertTrue(spots.example_parks("DE")["park"].startswith("DE-"))
        self.assertEqual(spots.example_parks("ZZ")["park"], "US-0001")       # no parks: US
        self.assertIn("JP", spots.countries())

    def test_strings_use_the_examples(self):
        lang = i18n._lang
        i18n.set_lang("en")
        i18n.examples = spots.example_parks("DE")
        try:
            self.assertIn(i18n.examples["park"], i18n.t("api.badPark"))
        finally:
            i18n.examples = {}
            i18n.set_lang(lang)


if __name__ == "__main__":
    unittest.main()


class GridTest(unittest.TestCase):
    def test_grid_center(self):
        from potacommon import grid_center
        self.assertEqual(grid_center("PM95rq"), (35.6875, 139.4583))      # Fuchu, Tokyo
        self.assertEqual(grid_center("fn54VH"), (44.3125, -68.2083))      # Acadia
        self.assertEqual(grid_center("PM95"), (35.5, 139))
        self.assertIsNone(grid_center("")); self.assertIsNone(grid_center("ZZ99aa")); self.assertIsNone(grid_center("PM95zz"))


class ParkStatusTest(unittest.TestCase):
    def test_status_from_the_shipped_list(self):
        self.assertEqual([spots.park_status(r) for r in ("JP-1281", "JP-0104", "JP-99999")], ["active", "retired", "no"])

    def test_unknown_number_only_when_pota_app_answered(self):
        saved = spots.fetch_json
        try:
            spots.fetch_json = lambda *a, **k: None                    # pota.app: no such park
            self.assertIs(spots.park_info("XX-99991").get("listed"), False)

            def offline(*a, **k):
                raise OSError("offline")
            spots.fetch_json = offline                                  # can't ask: say nothing
            self.assertNotIn("listed", spots.park_info("XX-99992"))
            self.assertNotIn("listed", spots.park_info("JP-1281"))     # in the list: no request at all
        finally:
            spots.fetch_json = saved
