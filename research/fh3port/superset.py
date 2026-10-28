"""Does every drawn mesh's layout mask contain its shader's full input mask (DBLS VDCL entry = union of the per-pass
LSCE masks)? FH2 cars vs a ported car. usage: superset.py [n_fh2_cars] [car.zip ...]"""
import zipfile, struct, sys, os, glob, random, collections

HERE = os.path.dirname(os.path.abspath(__file__))
FH3PORT = os.path.abspath(os.path.join(HERE, "..", "..", "fh3port"))
if FH3PORT not in sys.path:
    sys.path.insert(0, FH3PORT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bundle, vlayfix, lightparams
from fh3port import FH2_LIB, FH2_SHADERS, FH2
from vdclgroups import groups
from matidump import s7
M = os.path.join(FH2, "cars")


def required(sd):
    full, union = None, 0
    for tag, mv, hdr, ms in groups(sd):
        for h, f in ms:
            if tag == b"DBLS":
                full = int(f, 16)
            else:
                union |= int(f, 16)
    return full, union


def scan(zp, car, c, ex):
    z = zipfile.ZipFile(zp)
    names = {n.lower(): n for n in z.namelist()}
    res = lightparams.Resolver(names, z.read, car, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS)
    cache = {}
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not n.lower().startswith("scene/"):
            continue
        try:
            bl = bundle.parse(z.read(n))
        except ValueError:
            continue
        vl = [vlayfix.parse_vlay(b.data)[1] for b in bl if b.tag == b"yaLV"]
        mats = {}
        for b in bl:
            if b.tag == b"ItaM":
                for ib in bundle.parse(b.data):
                    if ib.tag == b"ITAM":
                        mats[vlayfix._id(b)] = s7(ib.data, 0)[0]
        for b in bl:
            if b.tag != b"hseM":
                continue
            mid, bone, flags, last, first, bucket, order = struct.unpack_from("<hhHBBHB", b.data, 0)
            if mid < 0 or not flags or mid not in mats:
                continue
            mp = mats[mid]
            if mp not in cache:
                md = res.material_bytes(mp)
                sp = res.shader_of_material(md) if md else None
                sd = res.shader_bytes(sp) if sp else None
                cache[mp] = (required(sd) if sd else (None, 0), (sp or "?").split("\\")[-1])
            (full, union), sh = cache[mp]
            m, lid = vlayfix._mesh_layout(b.data, b.ver)
            mk = vl[lid] if 0 <= lid < len(vl) else 0
            if full is None:
                c["no shader/DBLS"] += 1
                continue
            c["full==union" if full == union else "full!=union"] += 1
            ok = mk & full == full
            c["superset of full" if ok else "MISSING inputs"] += 1
            if not ok and len(ex) < 400:
                ex.append((os.path.basename(zp), n.split("/")[-1], sh, hex(mk), hex(full)))


if __name__ == "__main__":
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    zips = [z for z in glob.glob(M + r"\*_*.zip") if "NSX_16" not in z and "fh3tire" not in z.lower()]
    random.seed(21)
    c, ex = collections.Counter(), []
    for zp in random.sample(zips, k):
        scan(zp, os.path.basename(zp)[:-4], c, ex)
    print("FH2 (%d cars)" % k, dict(c))
    for e in ex[:15]:
        print("  ", e)
    for zp in sys.argv[2:]:
        c, ex = collections.Counter(), []
        scan(zp, "ACU_NSX_16" if "nsx" in zp.lower() else os.path.basename(zp)[:-4], c, ex)
        print(os.path.basename(zp), dict(c))
        for e in collections.Counter((e[1], e[2], e[3], e[4]) for e in ex).most_common(40):
            print("  ", e)
