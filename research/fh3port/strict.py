"""Per mesh: its own layout's slot sizes must equal the strides of the buffers it binds (and binding strides)."""
import zipfile, struct, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
FH3PORT = os.path.abspath(os.path.join(HERE, "..", "..", "fh3port"))
if FH3PORT not in sys.path:
    sys.path.insert(0, FH3PORT)

import bundle, vlayfix
z = zipfile.ZipFile(sys.argv[1]); bad = models = meshes = 0
for n in z.namelist():
    if not n.lower().endswith(".modelbin"): continue
    blobs = bundle.parse(z.read(n)); models += 1
    vl = dict(enumerate(vlayfix.parse_vlay(b.data)[0] for b in blobs if b.tag == b"yaLV"))
    vb = {vlayfix._id(b): struct.unpack_from("<IIHHI", b.data, 0) for b in blobs if b.tag == b"BreV"}
    for b in blobs:
        if b.tag != b"hseM": continue
        m, lid = vlayfix._mesh_layout(b.data, b.ver)
        if lid not in vl: continue
        meshes += 1
        for bid, slot, stride, off in m["bindings"]:
            want = sum(vlayfix.SIZE.get(e["fmt"], 0) for e in vl[lid] if e["slot"] == slot)
            have = vb.get(bid, (0, 0, 0))[2]
            if bid in vb and (want != have or stride != have):
                bad += 1
                if bad <= 10: print("MISMATCH", n.split("/")[-1], "layout", lid, "slot", slot, "layout bytes", want, "buffer", bid, "stride", have, "binding", stride)
print("models", models, "meshes", meshes, "mismatches", bad)
