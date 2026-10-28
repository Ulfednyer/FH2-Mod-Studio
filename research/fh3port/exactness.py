"""How often does a mesh's vertex-layout mask exactly equal one of its shader's VDCL masks? (FH2 cars vs NSX)"""
import zipfile, struct, sys, os, glob, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom, slod
import meshcheck as mc


def classify(zp, car):
    z = zipfile.ZipFile(zp); c = collections.Counter(); ex = collections.Counter()
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not n.lower().startswith("scene/"): continue
        try: hs, ents = geom.read_bundle(z.read(n))
        except Exception: continue
        vl = {geom.blob_id(e): struct.unpack_from("<I", e.data, len(e.data) - 4)[0] for e in ents if e.tag == "VLay"}
        mats = slod.material_paths(ents)
        for e in ents:
            if e.tag != "Mesh": continue
            mid = struct.unpack_from("<h", e.data, 0)[0]
            if mid < 0: continue
            try: m = geom.parse_mesh(e.data, e.ver)
            except Exception: continue
            mask = vl.get(struct.unpack_from("<i", e.data, m["bind_off"] - 8)[0])
            mp = mats.get(mid)
            sm = mc.shader_masks(mp, zp, car) if mp else None
            if mask is None or not sm or not sm[1]: continue
            if mask in sm[1]: c["exact"] += 1
            elif any(f and (f & ~mask) == 0 for f in sm[1]): c["superset"] += 1; ex[(sm[0].split("\\")[-1], hex(mask))] += 1
            else: c["bare-only"] += 1
    return c, ex


if __name__ == "__main__":
    tot = collections.Counter(); exs = collections.Counter()
    zips = sorted(glob.glob(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\*_*.zip"))
    random.seed(3)
    for zp in random.sample([z for z in zips if "NSX_16" not in z and "fh3tire" not in z.lower()], int(sys.argv[1]) if len(sys.argv) > 1 else 8):
        car = os.path.basename(zp)[:-4]
        c, ex = classify(zp, car); tot += c; exs += ex
        print("%-28s %s" % (car, dict(c)))
    print("FH2 total", dict(tot))
    for k, v in exs.most_common(8): print("   superset example", v, k)
