"""Which vertex channels of the installed car were invented by vlayfix (absent in the pre-vlayfix build), per
material/shader. usage: synth.py <installed.zip> <prevlay.zip> [car]"""
import zipfile, struct, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix, lightparams
from fh3port import FH2_LIB, FH2_SHADERS
from matidump import s7


def meshes(zp, car):
    z = zipfile.ZipFile(zp)
    names = {n.lower(): n for n in z.namelist()}
    res = lightparams.Resolver(names, z.read, car, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS)
    out = {}
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"):
            continue
        bl = bundle.parse(z.read(n))
        vls = [vlayfix.parse_vlay(b.data)[0] for b in bl if b.tag == b"yaLV"]
        mats = {}
        for b in bl:
            if b.tag == b"ItaM":
                try:
                    for ib in bundle.parse(b.data):
                        if ib.tag == b"ITAM":
                            mats[vlayfix._id(b)] = s7(ib.data, 0)[0]
                except ValueError:
                    pass
        k = 0
        for b in bl:
            if b.tag != b"hseM":
                continue
            mid, bone, flags = struct.unpack_from("<hhH", b.data, 0)
            m, lid = vlayfix._mesh_layout(b.data, b.ver)
            if mid >= 0 and flags:
                mp = mats.get(mid, "?")
                md = res.material_bytes(mp) if mp != "?" else None
                sp = (res.shader_of_material(md) or "?") if md else "?"
                chans = {"%s%d" % (e["sem"][0], e["idx"]) for e in vls[lid] if e["sem"] in ("TEXCOORD", "TANGENT")}
                out[(n, k)] = (mp.split("\\")[-1], sp.split("\\")[-1], chans)
            k += 1
    return out


car = sys.argv[3] if len(sys.argv) > 3 else "ACU_NSX_16"
now, before = meshes(sys.argv[1], car), meshes(sys.argv[2], car)
c = collections.Counter()
for key, (mat, sh, ch) in now.items():
    if key not in before:
        continue
    added = ch - before[key][2]
    if added:
        c[(mat, sh, " ".join(sorted(added)))] += 1
for (mat, sh, a), v in sorted(c.items(), key=lambda x: -x[1]):
    print("%4d  %-36s %-44s invented: %s" % (v, mat[:36], sh[:44], a))
