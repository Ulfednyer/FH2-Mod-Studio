"""Distance from triangle centroids of mesh A to the nearest triangle centroid of mesh B (rough coplanarity gauge).
usage: gap.py <car.zip> <modelA>:<meshIndex> <modelB>:<meshIndex>"""
import zipfile, struct, sys, os
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom


def tris(z, model, mi):
    n = next(x for x in z.namelist() if x.lower().endswith(model.lower()))
    hs, ents = geom.read_bundle(z.read(n))
    bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
    ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
    e = ents[mi]
    m = geom.parse_mesh(e.data, e.ver)
    for bid, slot, stride, off in m["bindings"]:
        b = bufs.get(bid)
        if b is None: continue
        cnt, sz, st, nel, fmt = struct.unpack_from("<IIHHI", b.data, 0)
        if fmt == 6 and st == 12:
            P = np.frombuffer(b.data[16:16 + cnt * 12], "<f4").reshape(-1, 3); first = off // stride; break
    ib = ibs[m["index_buffer"]]
    cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
    idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
    idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"] + first
    return P[idx.reshape(-1, 3)]


z = zipfile.ZipFile(sys.argv[1])
A = tris(z, *sys.argv[2].split(":")[:1], int(sys.argv[2].split(":")[1]))
B = tris(z, *sys.argv[3].split(":")[:1], int(sys.argv[3].split(":")[1]))
# point-to-plane distance from A's centroids to B's nearest triangle (by centroid)
ca, cb = A.mean(1), B.mean(1)
nb = np.cross(B[:, 1] - B[:, 0], B[:, 2] - B[:, 0]); nb /= np.linalg.norm(nb, axis=1, keepdims=True) + 1e-12
d = []
for p in ca:
    k = np.argmin(((cb - p) ** 2).sum(1))
    if np.linalg.norm(cb[k] - p) < 0.02:
        d.append(abs(np.dot(p - B[k, 0], nb[k])))
d = np.array(d)
print("A tris %d, near B: %d; plane distance mm: min %.3f median %.3f max %.3f" % (len(A), len(d), d.min() * 1000, np.median(d) * 1000, d.max() * 1000) if len(d) else "no nearby triangles")
print("bbox A", A.reshape(-1, 3).min(0), A.reshape(-1, 3).max(0))
