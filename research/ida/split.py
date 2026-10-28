import json, os, re, sys
from collections import Counter

here = os.path.dirname(os.path.abspath(__file__))
work = json.load(open(os.path.join(here, "worklist.json")))
NOISE = re.compile(r"Audio|Upgrade|Camera|CCam|Presentation|Render|HUD|ViewModel|XP|Skills|BoostCollection|BoostItem|Blur|Scene::|Nerd::|LOD|Gauge|UI", re.I)
keep = [w for w in work if not NOISE.search(w["class"])]
by_cls = {}
for w in keep:
    by_cls.setdefault(w["class"], []).append(w)
# two halves, whole classes, balanced by code size
a, b, sa, sb = [], [], 0, 0
for c, ws in sorted(by_cls.items(), key=lambda kv: -sum(w["size"] for w in kv[1])):
    s = sum(w["size"] for w in ws)
    (a, b)[sa > sb].extend(ws)
    if sa > sb:
        sb += s
    else:
        sa += s
for tag, part in (("a", a), ("b", b)):
    part.sort(key=lambda w: (w["class"], w["slot"]))
    json.dump(part, open(os.path.join(here, "work_%s.json" % tag), "w"), indent=0)
    with open(os.path.join(here, "dec_in_%s.txt" % tag), "w") as fh:
        fh.write("".join("%s  # %s slot %d\n" % (w["addr"], w["class"], w["slot"]) for w in part))
print("kept", len(keep), "of", len(work), "| a:", len(a), sa, "bytes | b:", len(b), sb, "bytes")
print(sorted(Counter(w["class"] for w in keep).items()))
