"""The data folder of 1.x (POTA Upload Helper) is moved to the new name on first start."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", tempfile.mkdtemp())
import potacommon  # noqa: E402


class DataFolderMoves(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.old = os.path.join(self.base, potacommon.OLD_NAME)
        self.new = os.path.join(self.base, potacommon.APP_NAME)

    def test_old_folder_is_renamed_with_its_files(self):
        os.makedirs(self.old)
        open(os.path.join(self.old, "qsolog.db"), "w").close()
        self.assertEqual(potacommon._moved(self.new, self.old), self.new)
        self.assertTrue(os.path.exists(os.path.join(self.new, "qsolog.db")))
        self.assertFalse(os.path.exists(self.old))

    def test_new_folder_wins_and_old_is_left_alone(self):
        os.makedirs(self.old)
        os.makedirs(self.new)
        self.assertEqual(potacommon._moved(self.new, self.old), self.new)
        self.assertTrue(os.path.exists(self.old))

    def test_fresh_install(self):
        self.assertEqual(potacommon._moved(self.new, self.old), self.new)


if __name__ == "__main__":
    unittest.main()
