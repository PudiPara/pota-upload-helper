import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", tempfile.mkdtemp())

from receiver import parse_packet  # noqa: E402
import qsolog  # noqa: E402


def qs(s):
    b = s.encode()
    return struct.pack(">I", len(b)) + b


class ReceiverTest(unittest.TestCase):
    def test_n1mm(self):
        x = (b'<?xml version="1.0"?><contactinfo><call>JA1AAA/P</call><timestamp>2026-10-20 02:26:05</timestamp>'
             b'<txfreq>704100</txfreq><mode>FT8</mode><snt>-05</snt><rcv>-10</rcv><ID>abc</ID></contactinfo>')
        (act, rec, uid), = parse_packet(x)
        self.assertEqual((act, uid, rec["CALL"], rec["BAND"], rec["TIME_ON"]), ("upsert", "abc", "JA1AAA/P", "40m", "022605"))


    def test_n1mm_delete(self):
        (act, rec, uid), = parse_packet(b"<?xml version='1.0'?><contactdelete><call>JA1AAA</call>"
                                        b"<timestamp>2026-10-20 02:26:05</timestamp></contactdelete>")
        self.assertEqual(act, "delete")

    def test_wsjtx(self):
        pkt = struct.pack(">III", 0xADBCCBDA, 2, 12) + qs("WSJT-X") + qs(
            "<call:6>JA2BBB <qso_date:8>20261020 <time_on:6>023000 <band:3>40m <mode:3>FT8 <eor>")
        self.assertEqual(parse_packet(pkt)[0][1]["CALL"], "JA2BBB")

    def test_adif_in_xml(self):
        r = parse_packet(b"<?xml version='1.0'?><QsoLoggedInfoAdif><Adif>&lt;CALL:6&gt;JA3CCC &lt;EOR&gt;</Adif></QsoLoggedInfoAdif>")
        self.assertEqual(r[0][1]["CALL"], "JA3CCC")

    def test_log_dedupe_and_delete(self):
        qsolog.upsert({"CALL": "JA4DDD/P", "QSO_DATE": "20261021", "TIME_ON": "010605", "BAND": "40m"}, "x1", "n1mm")
        qsolog.upsert({"CALL": "JA4DDD", "QSO_DATE": "20261021", "TIME_ON": "010500", "BAND": "40m"}, None, "wsjtx")
        self.assertEqual(len(qsolog.records(["20261021"])), 1)
        qsolog.delete("x1")
        self.assertEqual(len(qsolog.records(["20261021"])), 0)


class ParkInfo(unittest.TestCase):
    def test_shipped_list_answers_without_pota_app(self):
        from unittest import mock
        import spots
        with mock.patch.object(spots, "fetch_json", side_effect=AssertionError("no network")):
            p = spots.park_info("JP-1206")
            self.assertTrue(p["name"].startswith("Tama Kyuryo"))
            self.assertEqual(p["locations"], [{"code": "JP-TK", "name": "Tokyo"}])
            self.assertEqual(spots.common_locations("JP-1206")["options"], [{"code": "JP-TK", "name": "Tokyo"}])

    def test_a_park_newer_than_the_list_asks_pota_app(self):
        from unittest import mock
        import spots
        park = {"name": "New Park", "locationDesc": "US-MI,US-ND,US-NY", "grid6": "EN00",
                "locationName": "Michigan,New York,North Dakota"}       # pota.app: codes and names sorted apart
        with mock.patch.object(spots, "fetch_json", return_value=park), mock.patch.dict(spots._fetched, clear=True), \
                mock.patch.object(spots, "_shipped", {}):
            info = spots.park_info("US-99999")
            locs = info["locations"]
        self.assertEqual(info["name"], "New Park")
        self.assertEqual({l["code"]: l["name"] for l in locs},
                         {"US-MI": "Michigan", "US-ND": "North Dakota", "US-NY": "New York"})


if __name__ == "__main__":
    unittest.main()


class BindTest(unittest.TestCase):
    """Unicast listeners take packets from this computer only (CodeQL: no binding to all interfaces)."""

    def test_bind_address(self):
        from receiver import bind_address, membership_interface
        for win in (False, True):
            self.assertEqual(bind_address("", windows=win), "127.0.0.1")
            self.assertNotIn(bind_address("224.0.0.1", windows=win), ("", "0.0.0.0"))   # never every interface
        self.assertEqual(bind_address("224.0.0.1", windows=False), "224.0.0.1")
        self.assertEqual(bind_address("224.0.0.1", windows=True), "127.0.0.1")
        self.assertEqual(membership_interface(windows=True), "127.0.0.1")
        self.assertEqual(membership_interface(windows=False), "0.0.0.0")

    def test_unicast_listener_receives_on_loopback_only(self):
        import socket
        import time
        from receiver import Receiver
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        got = []
        rx = Receiver([{"name": "t", "port": port, "multicast": "", "enabled": True, "forward": ""}],
                      lambda a, r, u, n: got.append(r["CALL"]))
        rx.start()
        try:
            for _ in range(20):
                if rx.state.get("t", {}).get("code") == "listening":
                    break
                time.sleep(0.05)
            self.assertEqual(rx.state["t"]["code"], "listening")
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(
                b"<call:6>JA1AAA <qso_date:8>20261020 <time_on:4>0100 <band:3>40m <mode:3>FT8 <eor>", ("127.0.0.1", port))
            for _ in range(40):
                if got:
                    break
                time.sleep(0.05)
            self.assertEqual(got, ["JA1AAA"])
        finally:
            rx.stop()


class QLogNotifications(unittest.TestCase):
    def test_insert_update_delete(self):
        import json
        def msg(op):
            return json.dumps({"appid": "QLog", "msgtype": "QSO", "time": 1, "logid": "{abc}",
                               "data": {"operation": op, "rowid": 355, "type": "adif",
                                        "value": "<call:6>OK1ABC<qso_date:8:D>20220320<time_on:6>101500<band:3>30m<mode:2>CW<eor>"}}).encode()
        (a, r, uid), = parse_packet(msg("insert"))
        self.assertEqual((a, r["CALL"], r["QSO_DATE"], r["BAND"], r["MODE"], uid), ("upsert", "OK1ABC", "20220320", "30m", "CW", "qlog:{abc}:355"))
        self.assertEqual(parse_packet(msg("update"))[0][0], "upsert")
        self.assertEqual(parse_packet(msg("delete"))[0][0], "delete")
        self.assertEqual(parse_packet(b'{"appid": "Other", "msgtype": "QSO"}'), [])

