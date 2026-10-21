import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import potacommon  # noqa: E402


class SaveSettingsTogether(unittest.TestCase):
    def test_parallel_saves_keep_every_key(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("POTAROO_DATA")
            os.environ["POTAROO_DATA"] = d
            try:
                ts = [threading.Thread(target=potacommon.save_settings, args=({"k%d" % i: i},)) for i in range(40)]
                [t.start() for t in ts]
                [t.join() for t in ts]
                s = potacommon.load_settings()
                self.assertEqual({k: s[k] for k in s if k.startswith("k")}, {"k%d" % i: i for i in range(40)})
            finally:
                if old is None:
                    os.environ.pop("POTAROO_DATA")
                else:
                    os.environ["POTAROO_DATA"] = old


if __name__ == "__main__":
    unittest.main()
