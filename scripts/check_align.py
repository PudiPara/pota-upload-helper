"""check_align.mjs's pixel part: check_align.py shot.png rows.json scale -> rows whose items' middles differ.
A framed item = its box middle; text = the middle of the rows of pixels that differ from the background."""
import json
import sys

from PIL import Image

img = Image.open(sys.argv[1]).convert("RGB")
rows = json.load(open(sys.argv[2], encoding="utf-8"))
S = float(sys.argv[3])
px, (W, H) = img.load(), img.size


def ink_middle(k):
    x0, y0 = max(0, int(k["x"] * S)), max(0, int(k["y"] * S))
    x1, y1 = min(W, int((k["x"] + k["w"]) * S)), min(H, int((k["y"] + k["h"]) * S))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    seen = {}
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            seen[px[x, y]] = seen.get(px[x, y], 0) + 1
    bg = max(seen, key=seen.get)
    inked = [y for y in range(y0, y1) if any(sum(abs(a - b) for a, b in zip(px[x, y], bg)) > 90 for x in range(x0, x1))]
    return (inked[0] + inked[-1]) / 2 / S if inked else None


out = []
for r in rows:
    mids = [(k, k["y"] + k["h"] / 2 if k["framed"] else ink_middle(k)) for k in r["kids"]]
    mids = [(k, m) for k, m in mids if m is not None]
    for i, (a, ma) in enumerate(mids):
        for b, mb in mids[i + 1:]:
            if min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]) <= min(a["h"], b["h"]) * 0.6:
                continue
            if abs(ma - mb) > 1.5:
                tag = lambda k: k["name"] + ("[box]" if k["framed"] else "")
                out.append("%s :: %s vs %s %+.1fpx" % (r["row"], tag(a), tag(b), ma - mb))
print("\n".join(dict.fromkeys(out)) or "(none)")
