"""Drawn meshes without TEXCOORD2 (the AO-map UV): installed car vs the FH3 original, per model, with AO-map status.
FH2's own exterior meshes always carry TEXCOORD2 (15 cars: 12,773 of 12,774). usage: notex2.py [car]"""
import zipfile, struct, collections, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix, carbin
car = sys.argv[1] if len(sys.argv) > 1 else "ACU_NSX_16"
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\%s.zip" % car
F3 = sys.argv[2] if len(sys.argv) > 2 else r"C:\Games\Forza Horizon 3\media\cars\%s.zip" % car  # or a pre-vlayfix zip (prevlay.py)


def masks(d):
    bl = bundle.parse(d)
    vl = [vlayfix.parse_vlay(b.data) for b in bl if b.tag == b"yaLV"]
    out = []
    for b in bl:
        if b.tag != b"hseM":
            continue
        mid, bone, flags, last, first, bucket, order = struct.unpack_from("<hhHBBHB", b.data, 0)
        if mid < 0 or not flags:
            continue
        m, lid = vlayfix._mesh_layout(b.data, b.ver)
        els = vl[lid][0] if 0 <= lid < len(vl) else []
        out.append("".join("%s%d" % (e["sem"][0], e["idx"]) for e in els if e["sem"][:4] in ("TEXC", "TANG")))
    return out


z, z3 = zipfile.ZipFile(M), zipfile.ZipFile(F3)
n3 = {n.lower(): n for n in z3.namelist()}
r = carbin.parse(z.read(next(n for n in z.namelist() if n.endswith(".carbin"))))
ao = {p.split("\\")[-1].lower(): a for _, p, a in r.ao_paths}
tot = 0
for n in z.namelist():
    l = n.lower()
    if not l.endswith(".modelbin") or not l.startswith("scene/"):
        continue
    a = masks(z.read(n))
    bad = [m for m in a if "T2" not in m]
    if not bad:
        continue
    tot += len(bad)
    b3 = collections.Counter(masks(z3.read(n3[l]))) if l in n3 else "missing"
    print("%-34s noT2 %3d/%-3d AO %-14s now %s\n%38s FH3 %s" % (n.split("/")[-1], len(bad), len(a),
          (ao.get(l.split("/")[-1]) or "-").split("\\")[-1][:14], dict(collections.Counter(bad)), "", dict(b3) if b3 != "missing" else b3))
print("total", tot)
