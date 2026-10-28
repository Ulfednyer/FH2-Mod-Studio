"""Find coplanar/overlapping meshes (z-fighting candidates) within models: pairs of drawn meshes whose triangles share
(almost) the same positions. usage: overlap.py <car.zip> <model-substring>"""
import zipfile, struct, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import load
import geom, slod

zp, keys = sys.argv[1], sys.argv[2].lower().split(",")
z = zipfile.ZipFile(zp)
meshes = []
for n in z.namelist():
    if not n.lower().endswith(".modelbin") or not any(k in n.lower() for k in keys):
        continue
    hs, ents = geom.read_bundle(z.read(n))
    mats = slod.material_paths(ents)
    bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
    ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
    for i, e in enumerate(ents):
        if e.tag != "Mesh":
            continue
        mid = struct.unpack_from("<h", e.data, 0)[0]
        flags, last, first, bucket = struct.unpack_from("<HBBH", e.data, 4)
        if not flags & 2:
            continue
        m = geom.parse_mesh(e.data, e.ver)
        pb = None
        for bid, slot, stride, off in m["bindings"]:
            b = bufs.get(bid)
            if b is None: continue
            cnt, sz, st, nel, fmt = struct.unpack_from("<IIHHI", b.data, 0)
            if fmt == 6 and st == 12:
                pb = (np.frombuffer(b.data[16:16 + cnt * 12], "<f4").reshape(-1, 3), off // stride if stride else 0); break
        ib = ibs.get(m["index_buffer"])
        if pb is None or ib is None: continue
        cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
        idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
        idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"] + pb[1]
        idx = idx[: len(idx) // 3 * 3].reshape(-1, 3)
        idx = idx[(idx < len(pb[0])).all(1)]
        cen = pb[0][idx].mean(1)
        keyset = set(map(tuple, np.round(cen, 3)))
        meshes.append((n.split("/")[-1][:14] + ":" + str(i), mats.get(mid, "?").split("\\")[-1], hex(bucket), len(idx), keyset))
if True:
    for a in range(len(meshes)):
        for b in range(a + 1, len(meshes)):
            A, B = meshes[a][4], meshes[b][4]
            common = len(A & B)
            if common and common >= 0.3 * min(len(A), len(B)) and "?" not in (meshes[a][1], meshes[b][1]):
                print("  overlap %4d tris: %-18s %-30s bucket %s (%d)  <->  %-18s %-30s bucket %s (%d)" % (
                    common, meshes[a][0], meshes[a][1][:30], meshes[a][2], meshes[a][3], meshes[b][0], meshes[b][1][:30], meshes[b][2], meshes[b][3]))
