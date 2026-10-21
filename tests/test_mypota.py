"""設定 → POTA の実績: pota.app's two CSVs, "New" parks and the next activation number."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", tempfile.mkdtemp())
import mypota  # noqa: E402
import potacommon  # noqa: E402

HUNTER = ('"DX Entity","Location","HASC","Reference","Park Name","First QSO Date","QSOs"\n'
          '"Japan","Tokyo","JP-TK","JP-1206","Tama Kyuryo Prefectural Nature Park","2025-08-03",3\n'
          '"Republic of Korea","Incheon","KR-IN","KR-0704","씨사이드파크\tSeaside Provincial Recreation Park","2025-08-10",1\n')
ACTIVATOR = ('"DX Entity","Location","HASC","Reference","Park Name","First QSO Date","Attempts","Activations","QSOs"\n'
             '"Japan","Tokyo","JP-TK","JP-1281","Fuchunomori Prefectural Park","2025-06-08",24,24,1011\n')


class MyPota(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()
        self.files = []
        for name, text in (("hunter_parks.csv", HUNTER), ("activator_parks.csv", ACTIVATOR), ("other.csv", "a,b\n1,2\n")):
            path = os.path.join(potacommon.DATA_DIR, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.files.append(path)

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def test_nothing_before_an_import(self):
        self.assertIsNone(mypota.first_hunted())
        self.assertEqual(mypota.new_parks(["JP-0001"], None), [])
        self.assertIsNone(mypota.activations("JP-1281"))

    def test_import_tells_the_two_files_apart_and_refuses_others(self):
        self.assertEqual(mypota.import_files(self.files[1::-1]), {"ok": True, "hunter": 2, "activator": 1})
        self.assertEqual(mypota.import_files([self.files[2]])["ok"], False)
        self.assertEqual(mypota.status()["hunter"]["n"], 2)

    def test_new_parks_grow_with_the_hunter_log_and_confirmed_p2p(self):
        mypota.import_files(self.files[:1])
        with open(potacommon.data_path("hunter.json"), "w", encoding="utf-8") as fh:
            json.dump([{"reference": "JP-0002", "date": "2026-10-20T01:00:00", "callsign": "JA1X", "band": "40m"}], fh)
        p2p = {"CALL": "JA1Y", "QSO_DATE": "20261021", "TIME_ON": "063000", "P2P_DECISION": "yes", "SIG_INFO": "JP-0003"}
        first = mypota.first_hunted([p2p])
        self.assertEqual(mypota.new_parks(["JP-1206", "JP-0002", "JP-0003", "JP-0004"], first), ["JP-0004"])
        # at the P2P QSO itself JP-0003 was still new: that is the moment it got hunted (Hunted!)
        self.assertEqual(mypota.new_parks(["JP-0003"], first, at="20261021063000"), ["JP-0003"])

    def test_next_activation_adds_the_app_days_after_the_import(self):
        mypota.import_files(self.files[1:2])
        self.assertEqual(mypota.activations("JP-0001")["next"], 1)
        a = mypota.activations("JP-1281", [("20990101", {"JP-1281": 12}), ("20000101", {"JP-1281": 5})])
        self.assertEqual((a["next"], a["done"], a["qsos"]), (26, 25, 1023))

    def test_record_marks_what_the_app_added(self):
        mypota.import_files(self.files[:2])
        p2p = {"CALL": "JA1Y", "QSO_DATE": "20991021", "TIME_ON": "063000", "P2P_DECISION": "yes", "SIG_INFO": "JP-0003"}
        rec = mypota.record([p2p], [("20991021", {"JP-1281": 12, "JP-0009": 3}), ("20991021", {"JP-0009": 8})])
        h = {r["ref"]: r for r in rec["hunted"]}
        self.assertEqual((h["JP-0003"]["source"], h["JP-0003"]["added"], h["JP-0003"]["first"]), ("app", True, "2099-10-21"))
        self.assertEqual((h["JP-1206"]["source"], h["JP-1206"]["added"], h["JP-1206"]["qsos"]), ("csv", False, 3))
        self.assertEqual(rec["hunted"][0]["ref"], "JP-0003")                      # newest first
        a = {r["ref"]: r for r in rec["activated"]}
        self.assertEqual((a["JP-1281"]["attempts"], a["JP-1281"]["added"], a["JP-1281"]["app"]), (25, False, 1))
        # two entries of one day are one activation: 3 + 8 QSOs = 11, a success
        self.assertEqual((a["JP-0009"]["attempts"], a["JP-0009"]["activations"], a["JP-0009"]["added"]), (1, 1, True))


if __name__ == "__main__":
    unittest.main()
