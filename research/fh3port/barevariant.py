"""Meshes whose vertex-layout mask matches no non-zero VDCL variant of their FH2 shader (only the bare 0x0 one).
usage: barevariant.py <car.zip> <car_name>"""
import zipfile, struct, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom, slod
import meshcheck as mc
zp, car = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zp)
bad = collections.Counter(); ok = collections.Counter(); per_part = collections.defaultdict(collections.Counter)
for n in z.namelist():
    if not n.lower().endswith(".modelbin"): continue
    hs, ents = geom.read_bundle(z.read(n))
    vl = {geom.blob_id(e): struct.unpack_from("<I", e.data, len(e.data) - 4)[0] for e in ents if e.tag == "VLay"}
    mats = slod.material_paths(ents)
    for e in ents:
        if e.tag != "Mesh": continue
        mid = struct.unpack_from("<h", e.data, 0)[0]
        if mid < 0: continue
        m = geom.parse_mesh(e.data, e.ver)
        mask = vl.get(struct.unpack_from("<i", e.data, m["bind_off"] - 8)[0])
        mp = mats.get(mid)
        sm = mc.shader_masks(mp, zp, car) if mp else None
        if mask is None or not sm or not sm[1]: continue
        fits = [f for f in sm[1] if f and (f & ~mask) == 0]
        key = (sm[0].split("\\")[-1].replace(".shaderbin", ""), hex(mask), tuple(sorted(hex(f) for f in sm[1] if f)))
        if fits:
            ok[key[0]] += 1
        else:
            bad[key] += 1
            per_part[n.split("/")[-1]][mp.split("\\")[-1]] += 1
print("meshes with a real variant:", sum(ok.values()), " only bare variant:", sum(bad.values()))
for k, v in bad.most_common(30): print("  %3d %-40s layout %-6s shader variants %s" % (v, k[0], k[1], k[2]))
print()
for p, c in sorted(per_part.items()): print("  %-38s %s" % (p, dict(c)))
