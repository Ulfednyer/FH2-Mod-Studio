import sys, os, zipfile, struct, collections
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
sys.path.insert(0, os.path.dirname(__file__))
import geom
from vdcl import vdcl_masks
MEDIA = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
_zips = {}
def zf(p):
    if p not in _zips:
        try:
            z = zipfile.ZipFile(p); _zips[p] = (z, {n.lower().replace("/", "\\"): n for n in z.namelist()})
        except Exception:
            _zips[p] = None
    return _zips[p]
def load(path, carzip, carname):
    p = path.lower().replace("/", "\\")
    head = "game:" + "\\" + "media" + "\\"
    if p.startswith(head): p = p[len(head):]
    pre = "cars" + "\\" + carname.lower() + "\\"
    if p.startswith(pre):
        z = zf(carzip)
        n = z[1].get(p[len(pre):])
        return z[0].read(n) if n else None
    parts = p.split("\\")
    for i in range(len(parts) - 1, 0, -1):
        cand = os.path.join(MEDIA, *parts[:i])
        for zp in [cand + ".zip"] + [cand + "_pri_%d.zip" % k for k in (44, 80)]:
            z = zf(zp) if os.path.exists(zp) else None
            if z:
                n = z[1].get("\\".join(parts[i:]))
                if n: return z[0].read(n)
    f = os.path.join(MEDIA, *parts)
    return open(f, "rb").read() if os.path.exists(f) else None
def str7(b, p):
    n = 0; s = 0
    while True:
        c = b[p]; p += 1; n |= (c & 0x7f) << s; s += 7
        if not c & 0x80: break
    return b[p:p+n].decode("latin1"), p + n
def anybundle(d):
    # returns [(tag, data)] for bundle 1.0 or 1.1
    maj, mi = d[4], d[5]
    if (maj, mi) == (1, 0): cnt = struct.unpack_from("<H", d, 6)[0]; eo = 16
    else: cnt = struct.unpack_from("<I", d, 16)[0]; eo = 20
    out = []
    for i in range(cnt):
        tag, vM, vm, mc, mo, do, sz = struct.unpack_from("<4sBBHIII", d, eo + 24 * i)
        out.append((tag[::-1].decode("latin1"), d[do:do+sz], (vM, vm), mo, mc))
    return out
_shader = {}
def shader_masks(matpath, carzip, carname):
    key = matpath.lower()
    if key in _shader: return _shader[key]
    res = None
    md = load(matpath, carzip, carname)
    if md:
        for tag, data, ver, mo, mc in anybundle(md):
            if tag == "MATL":
                p = 0; paths = []
                for _ in range(1 + (ver >= (1, 1)) + (ver >= (1, 2))):
                    s, p = str7(data, p); paths.append(s)
                sp = next((x for x in reversed(paths) if x), None)
                sd = load(sp, carzip, carname) if sp else None
                res = (sp, set(vdcl_masks(sd)) if sd else None)
    _shader[key] = res
    return res
def check(carzip, carname, verbose=False):
    z = zipfile.ZipFile(carzip)
    stats = collections.Counter(); bad = collections.Counter(); unres = collections.Counter()
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"): continue
        hs, ents = geom.read_bundle(z.read(n))
        vl = {geom.blob_id(e): struct.unpack_from("<I", e.data, len(e.data) - 4)[0] for e in ents if e.tag == "VLay"}
        mats = {}
        for e in ents:
            if e.tag == "MatI":
                inner = anybundle(e.data)
                path = next((str7(d, 0)[0] for t, d, *_ in inner if t == "MATI"), None)
                mats[geom.blob_id(e)] = path
        for e in ents:
            if e.tag != "Mesh": continue
            mid = struct.unpack_from("<h", e.data, 0)[0]
            m = geom.parse_mesh(e.data, e.ver)
            # layout index = u32 right before the binding count
            li = struct.unpack_from("<i", e.data, m["bind_off"] - 8)[0]
            mask = vl.get(li)
            mp = mats.get(mid)
            sm = shader_masks(mp, carzip, carname) if mp else None
            if mask is None or not sm or sm[1] is None:
                why = "no vlay" if mask is None else "no material id %d" % mid if not mp else "material not found" if not sm else "shader not found"
                stats["unresolved"] += 1
                unres[(why, (mp or "")[-70:], (sm[0] if sm else "")[-60:])] += 1
                continue
            masks = sm[1]
            if mask in masks: r = "exact"
            elif any((f & ~mask) == 0 for f in masks): r = "subset"
            else: r = "NONE"
            stats[r] += 1
            if r != "exact":
                bad[(n.split("/")[-1], hex(mask), sm[0].split("\\")[-1], tuple(sorted(hex(x) for x in masks))[:6])] += 1
    print(carzip.split("\\")[-1].split("/")[-1], dict(stats))
    for k, v in unres.most_common(15): print("  UNRESOLVED", v, k)
    for k, v in list(bad.items())[:25 if verbose else 8]: print("  ", v, k)
if __name__ == "__main__":
    check(sys.argv[1], sys.argv[2], len(sys.argv) > 3)
