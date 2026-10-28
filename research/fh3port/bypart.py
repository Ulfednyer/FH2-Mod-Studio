import sys, zipfile, struct, collections
sys.path.insert(0, ".")
import meshcheck as mc, geom
carzip, carname = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(carzip)
res = collections.defaultdict(collections.Counter)
shaders = collections.defaultdict(collections.Counter)
for n in z.namelist():
    if not n.lower().endswith(".modelbin"): continue
    hs, ents = geom.read_bundle(z.read(n))
    vl = {geom.blob_id(e): struct.unpack_from("<I", e.data, len(e.data) - 4)[0] for e in ents if e.tag == "VLay"}
    mats = {}
    for e in ents:
        if e.tag == "MatI":
            mats[geom.blob_id(e)] = next((mc.str7(d, 0)[0] for t, d, *_ in mc.anybundle(e.data) if t == "MATI"), None)
    for e in ents:
        if e.tag != "Mesh": continue
        mid = struct.unpack_from("<h", e.data, 0)[0]
        m = geom.parse_mesh(e.data, e.ver)
        mask = vl.get(struct.unpack_from("<i", e.data, m["bind_off"] - 8)[0])
        sm = mc.shader_masks(mats.get(mid), carzip, carname) if mats.get(mid) else None
        if mask is None or not sm or sm[1] is None: continue
        r = "exact" if mask in sm[1] else "subset" if any((f & ~mask) == 0 for f in sm[1]) else "NONE"
        part = n.split("/")[-1].replace(".modelbin", "")
        res[part][r] += 1
        shaders[(sm[0].split("\\")[-1], r)][hex(mask)] += 1
for p in sorted(res): print("%-40s %s" % (p, dict(res[p])))
print()
for k in sorted(shaders): print(k, dict(shaders[k]))
