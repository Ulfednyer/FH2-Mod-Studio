"""(shader, layout mask) combinations of a ported car that no FH2 car uses. usage: combos.py <n_fh2_cars> <car.zip>"""
import zipfile, struct, sys, os, glob, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import superset
from superset import M


def combos(zp, car):
    out = collections.Counter()
    orig = superset.scan.__globals__["vlayfix"]._mesh_layout
    z = zipfile.ZipFile(zp)
    names = {n.lower(): n for n in z.namelist()}
    res = superset.lightparams.Resolver(names, z.read, car, os.path.join(superset.FH2_LIB, "Materials.zip"), superset.FH2_SHADERS)
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not n.lower().startswith("scene/"):
            continue
        try:
            bl = superset.bundle.parse(z.read(n))
        except ValueError:
            continue
        vl = [superset.vlayfix.parse_vlay(b.data)[1] for b in bl if b.tag == b"yaLV"]
        mats = {}
        for b in bl:
            if b.tag == b"ItaM":
                try:
                    inner = superset.bundle.parse(b.data)
                except ValueError:
                    continue
                for ib in inner:
                    if ib.tag == b"ITAM":
                        mats[superset.vlayfix._id(b)] = superset.s7(ib.data, 0)[0]
        for b in bl:
            if b.tag != b"hseM":
                continue
            mid = struct.unpack_from("<h", b.data, 0)[0]
            if mid < 0 or mid not in mats:
                continue
            md = res.material_bytes(mats[mid])
            sp = res.shader_of_material(md) if md else None
            m, lid = orig(b.data, b.ver)
            out[((sp or "?").split("\\")[-1], hex(vl[lid]) if 0 <= lid < len(vl) else "?")] += 1
    return out


k = int(sys.argv[1])
zips = [z for z in glob.glob(M + r"\*_*.zip") if "NSX_16" not in z and "fh3tire" not in z.lower()]
random.seed(5)
fh2 = collections.Counter()
for zp in random.sample(zips, k):
    fh2 += combos(zp, os.path.basename(zp)[:-4])
car = combos(sys.argv[2], "ACU_NSX_16")
shaders2 = {s for s, m in fh2}
print("NSX combos never used by %d FH2 cars:" % k)
for (s, m), c in sorted(car.items()):
    if (s, m) not in fh2:
        print("  %-48s %-6s x%-4d FH2 uses this shader with: %s" % (s, m, c, sorted({mm for ss, mm in fh2 if ss == s}) or "SHADER UNUSED"))
