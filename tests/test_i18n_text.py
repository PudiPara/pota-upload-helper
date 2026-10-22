"""A status line made in one language shows in the language chosen later (i18n.Text)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import i18n  # noqa: E402


class LazyText(unittest.TestCase):
    def tearDown(self):
        i18n.set_lang("ja")

    def test_follows_the_language(self):
        i18n.set_lang("de")
        msg = i18n.Text("spot.updated", time="12:00", n=5)
        de = str(msg)
        i18n.set_lang("en")
        self.assertEqual(str(msg), i18n.t("spot.updated", time="12:00", n=5))
        self.assertNotEqual(str(msg), de)


if __name__ == "__main__":
    unittest.main()
