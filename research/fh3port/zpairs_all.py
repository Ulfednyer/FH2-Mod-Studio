"""All opaque/transparent mesh pairs in a model sharing a LOD, with plane distance stats (mm).
usage: zpairs.py <car.zip> <model-substring>"""
import zipfile, struct, sys
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom, zfight, slod
z = zipfile.ZipFile(sys.argv[1])
n = next(x for x in z.namelist() if sys.argv[2].lower() in x.lower())
hs, ents = geom.read_bundle(z.read(n))
mats = slod.material_paths(ents)
bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}; ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
ms = []
for i, e in enumerate(ents):
    if e.tag != "Mesh": continue
    mid = struct.unpack_from("<h", e.data, 0)[0]
    flags, last, first, bucket = struct.unpack_from("<HBBH", e.data, 4)
    if mid < 0 or not flags: continue
    g = zfight._mesh_geometry(ents, e, bufs, ibs)
    if not g: continue
    cnt = struct.unpack_from("<I", bufs[g[0]].data, 0)[0]
    P = np.frombuffer(bufs[g[0]].data[16:16 + cnt * 12], "<f4").reshape(-1, 3)
    ms.append((i, flags, bucket, mats.get(mid, "?").split("\\")[-1][:26], P[g[1]]))
for a in ms:
    pass
    for b in ms:
        if b[0] <= a[0] or not (a[1] & b[1]): continue
        ca = a[4].mean(1); G = b[4]; cg = G.mean(1)
        ng = np.cross(G[:, 1] - G[:, 0], G[:, 2] - G[:, 0]); ng /= np.linalg.norm(ng, axis=1, keepdims=True) + 1e-12
        d = []
        for p in ca:
            k = np.argmin(((cg - p) ** 2).sum(1))
            if np.linalg.norm(cg[k] - p) < 0.02: d.append(abs(np.dot(p - G[k, 0], ng[k])) * 1000)
        if len(d) >= 0.3 * len(ca) and np.median(d) < 5:
            print("A %3d %-26s flags %-5s  B %3d %-26s flags %-5s  near %3d/%3d  median %.3f mm  min %.3f" % (
                a[0], a[3], hex(a[1]), b[0], b[3], hex(b[1]) + " b" + hex(b[2]), len(d), len(ca), np.median(d), min(d)))
