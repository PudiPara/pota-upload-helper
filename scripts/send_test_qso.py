#!/usr/bin/env python3
"""Send a fake "logged QSO" to a listener of the app, for development.

    scripts/send_test_qso.py 22237 JS6UHQ/6            # WSJT-X "Logged ADIF" (msg 12), now, 40m FT8
    scripts/send_test_qso.py 22237 JA1TST --n1mm       # N1MM <contactinfo> like RUMlogNG sends
    scripts/send_test_qso.py 22237 JA1TST --delete     # N1MM <contactdelete>

Use a port only the dev app listens on (e.g. 22237). Never send to 2237 or
2333/2334: RUMlogNG and other loggers on this Mac listen there and would log it.
"""
import datetime as dt
import socket
import struct
import sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
if len(args) < 2:
    sys.exit(__doc__)
port, call = int(args[0]), args[1].upper()
if port in (2237, 2333, 2334):
    sys.exit("refusing to send to port %d: real loggers listen there" % port)
now = dt.datetime.now(dt.timezone.utc)
d, t = now.strftime("%Y%m%d"), now.strftime("%H%M%S")

if "--n1mm" in flags or "--delete" in flags:
    tag = "contactdelete" if "--delete" in flags else "contactinfo"
    pkt = ('<?xml version="1.0" encoding="utf-8"?><%s><app>RUMlogNG</app><timestamp>%s</timestamp>'
           '<mycall>JL1FVA</mycall><call>%s</call><txfreq>703000</txfreq><rxfreq>703000</rxfreq>'
           '<band>7</band><mode>CW</mode><snt>599</snt><rcv>599</rcv><ID>dev-%s</ID></%s>'
           % (tag, now.strftime("%Y-%m-%d %H:%M:%S"), call, call, tag)).encode()
else:
    def qs(s):
        b = s.encode()
        return struct.pack(">I", len(b)) + b
    adif = "<call:%d>%s <qso_date:8>%s <time_on:6>%s <band:3>40m <mode:3>FT8 <eor>" % (len(call), call, d, t)
    pkt = struct.pack(">III", 0xADBCCBDA, 2, 12) + qs("WSJT-X") + qs(adif)

socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(pkt, ("127.0.0.1", port))
print("sent %s %sZ to 127.0.0.1:%d" % (call, t, port))
