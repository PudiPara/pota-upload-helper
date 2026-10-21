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
