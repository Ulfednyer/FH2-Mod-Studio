import re
d = open(r"C:\Users\opsuc\Downloads\amzimuth\data\logs\20261018T184924-651-31104.dmp", "rb").read()
print("dump size", len(d))
needles = ["acu_nsx_16.zip", "rcfh3", "fh3tire", "tire_wet_c", "tire_b_horizon", "_library\\textures.zip", "gamedbrc", "zipmanifest"]
for n in needles:
    for enc in ("ascii", "utf-16le"):
        pat = n.encode(enc)
        hits = [m.start() for m in re.finditer(re.escape(pat), d, re.I)]
        if hits:
            p = hits[0]
            ctx = d[max(0, p - 80):p + len(pat) + 40]
            print("%-24s %-8s %3d hits, first ctx: %r" % (n, enc, len(hits), ctx.decode(enc, "replace").replace("\x00", "")[-160:]))
# last game: paths in the dump (ascii) - what was being mounted
paths = re.findall(rb"game:\\\\?media\\\\?[\w\\\. +-]{3,120}", d, re.I)
seen = []
for p in paths:
    s = p.decode()
    if s.lower() not in [x.lower() for x in seen]:
        seen.append(s)
print("distinct game: paths in dump:", len(seen))
for s in seen[-40:]:
    print("  ", s)
