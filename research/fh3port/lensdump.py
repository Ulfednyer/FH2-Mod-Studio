"""Mesh-level dump (LOD flags, bucket, material, shader, layout mask, triangles) for models matching a substring.
usage: lensdump.py <car.zip> <car_name> <model-substring,...>"""
import zipfile, struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix, geom
import meshcheck as mc
zp, car, keys = sys.argv[1], sys.argv[2], sys.argv[3].lower().split(",")
z = zipfile.ZipFile(zp)
for n in z.namelist():
    if not n.lower().endswith(".modelbin") or not any(k in n.lower() for k in keys):
        continue
    blobs = bundle.parse(z.read(n))
    vl = dict(enumerate(vlayfix.parse_vlay(b.data)[1] for b in blobs if b.tag == b"yaLV"))
    mats = {}
    for b in blobs:
        if b.tag == b"ItaM":
            for ib in bundle.parse(b.data):
                if ib.tag == b"ITAM":
                    mats[vlayfix._id(b)] = mc.str7(ib.data, 0)[0]
    modl = next(b for b in blobs if b.tag == b"ldoM")
    print("=====", n, "Modl", modl.ver, modl.data[:14].hex())
    for b in blobs:
        if b.tag != b"hseM":
            continue
        mid, bone, flags, last, first, bucket, order = struct.unpack_from("<hhHBBHB", b.data, 0)
        m, lid = vlayfix._mesh_layout(b.data, b.ver)
        mp = mats.get(mid)
        sm = mc.shader_masks(mp, zp, car) if mp else None
        print("  mat %3d %-34s shader %-34s flags %-5s lod %3d..%-3d bucket %-5s order %3d mask %-6s exact %-5s tris %d" % (
            mid, (mp or "-").split("\\")[-1][:34], (sm[0].split("\\")[-1] if sm else "-")[:34], hex(flags), first, last,
            hex(bucket), order, hex(vl.get(lid, -1)), (vl.get(lid) in sm[1]) if sm and sm[1] else "-", m["index_count"] // 3))
