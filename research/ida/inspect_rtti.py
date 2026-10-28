import json, sys
from collections import Counter

recs = json.load(open(sys.argv[1]))
pat = sys.argv[2] if len(sys.argv) > 2 else None
if pat:
    for r in recs:
        if pat.lower() in r["class"].lower():
            print(r["class"], r["vft"], "off", r["offset"], "n=%d" % len(r["funcs"]), "bases:", r["bases"][:4], r["funcs"][:12])
else:
    top = Counter(r["class"].split("::")[0] if "::" in r["class"] else "<global>" for r in recs)
    print("namespaces:", top.most_common(25))
    print("vfunc count dist:", Counter(min(len(r["funcs"]), 50) // 10 * 10 for r in recs))
    print("zero-entry vftables:", sum(1 for r in recs if not r["funcs"]))
