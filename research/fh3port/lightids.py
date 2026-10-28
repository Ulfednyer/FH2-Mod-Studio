"""Light-function ids used by car materials/instances: FH2 cars vs the NSX (per model group: headlight/taillight/...)."""
import zipfile, struct, sys, glob, random, collections, re
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
FN = {0x493073A0: "LightFunction", 0x19416CFE: "FH3 Light Parameter"}
src = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port\paramnames.json", encoding="utf-8").read()
import json
names = {int(h, 16): n for h, n in json.loads(src)["names"].items()}
for h, n in names.items():
    if n in ("LightFunctionB",):
        FN[h] = n
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"


def group(n):
    n = n.lower()
    for k in ("headlight", "taillight", "glasslhl", "glassrhl", "glassltl", "glassrtl", "chmsl", "sidemarker", "fog", "reverse", "plate", "gauge", "dash"):
        if k in n: return k
    return "other"


def walk(d, out, model):
    for tag, ver, ep, doff, size in mtpr.blobs(d):
        b = d[doff:doff + size]
        if tag[::-1] == b"MTPR":
            ps, _ = mtpr.parse_params(b, None)
            for s, e, maj, mn, h, typ in ps:
                if h in FN and typ == 4:
                    out[(group(model), FN[h], struct.unpack_from("<i", b, s + 7 + (16 if maj >= 3 else 0))[0])] += 1
        elif tag[::-1] == b"MatI":
            walk(b, out, model)


def scan(zp, out):
    z = zipfile.ZipFile(zp)
    for n in z.namelist():
        if n.lower().endswith(".modelbin"):
            try: walk(z.read(n), out, n)
            except Exception: pass


fh2 = collections.Counter(); nsx = collections.Counter(); fh3 = collections.Counter()
zips = [z for z in glob.glob(M + r"\*_*.zip") if "NSX_16" not in z and "fh3tire" not in z.lower()]
random.seed(7)
for zp in random.sample(zips, 25): scan(zp, fh2)
scan(M + r"\ACU_NSX_16.zip", nsx)
scan(r"C:\Games\Forza Horizon 3\media\cars\ACU_NSX_16.zip", fh3)
for name, c in (("FH2 (25 cars)", fh2), ("NSX installed", nsx), ("NSX FH3 original", fh3)):
    print("==", name)
    g = collections.defaultdict(list)
    for (grp, p, v), cnt in sorted(c.items()): g[(grp, p)].append("%d:%d" % (v, cnt))
    for k, v in sorted(g.items()): print("  %-12s %-22s %s" % (k[0], k[1], ", ".join(v)))
