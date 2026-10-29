"""Offline render of an installed car as FH2 assembles it: every carbin model entry (its 4x4 transform) x the modelbin's
LOD0 meshes. Colours: one per model, or by origin (FH1-converted vs donor) with --origin.
    py carrender.py <car zip> <out prefix> [views=side,front,top] [--origin <donor zip> <car> <donor>] [--only a,b] [--donor-only]
Writes <out prefix>_<view>.png and prints the legend."""
import os
import struct
import sys
import zipfile

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "..", "fh3port")))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "fh3port")))
import carbin
import geom
import render


def entries(cb):
    """[(model path, 4x4 matrix, lod mask)] in carbin order."""
    out = []
    orig = carbin.model

    def model(r):
        start = r.p
        r.u16()
        path = r.s()
        mat = np.array(struct.unpack_from("<16f", r.d, r.p)).reshape(4, 4)
        r.p = start
        p = orig(r)
        out.append((p, mat))
        return p
    carbin.model = model
    try:
        r = carbin.parse(cb)
    finally:
        carbin.model = orig
    masks = {path: struct.unpack_from("<H", cb, off)[0] for off, path in r.lod_masks}
    return [(p, m, masks.get(p, 0)) for p, m in out]


def triangles(d, lodbit=1):
    hs, ents = geom.read_bundle(d)
    bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
    ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
    tris = []
    for e in ents:
        if e.tag != "Mesh" or struct.unpack_from("<h", e.data, 0)[0] < 0:
            continue
        if lodbit and not struct.unpack_from("<H", e.data, 4)[0] & lodbit:
            continue
        m = geom.parse_mesh(e.data, e.ver)
        pb = None
        for bid, slot, stride, off in m["bindings"]:
            b = bufs.get(bid)
            if b is not None:
                cnt, sz, st, nel, fmt = struct.unpack_from("<IIHHI", b.data, 0)
                if fmt == 6 and st == 12:
                    pb = np.frombuffer(b.data[16:16 + cnt * 12], "<f4").reshape(-1, 3)
                    first = off // stride if stride else 0   # binding byte offset = the mesh's first vertex
                    break
        ib = ibs.get(m["index_buffer"])
        if pb is None or ib is None:
            continue
        cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
        idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
        idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"] + first
        idx = idx[: len(idx) // 3 * 3].reshape(-1, 3)
        idx = idx[(idx < len(pb)).all(1)]
        tris.append(pb[idx])
    return np.concatenate(tris) if tris else np.zeros((0, 3, 3))


def main(argv):
    zp, prefix = argv[0], argv[1]
    views = argv[2].split(",") if len(argv) > 2 and not argv[2].startswith("--") else ["side", "front", "top"]
    fh1 = None
    only = None
    if "--origin" in argv:
        i = argv.index("--origin")
        donor_zp, car, donor = argv[i + 1:i + 4]
        with zipfile.ZipFile(zp) as a, zipfile.ZipFile(donor_zp) as b:
            bn = {n.lower().replace(donor.lower(), car.lower()): n for n in b.namelist()}
            fh1 = {n.lower() for n in a.namelist() if n.lower() in bn and a.read(n) != b.read(bn[n.lower()])}
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].lower().split(",")
    z = zipfile.ZipFile(zp)
    names = {n.lower(): n for n in z.namelist()}
    cb = next(n for n in z.namelist() if n.lower().endswith(".carbin"))
    T, M, legend, cache = [], [], [], {}
    for path, mat, mask in entries(z.read(cb)):
        rel = path.lower().split("\\", 4)[-1].replace("\\", "/")   # game:\media\cars\<car>\<rel>
        if rel not in names or (only and not any(k in rel for k in only)) or mask == 0:   # mask 0 = hidden
            continue
        if "--donor-only" in argv and fh1 is not None and rel in fh1:
            continue
        if rel not in cache:
            cache[rel] = triangles(z.read(names[rel]))
        t = cache[rel]
        if not len(t):
            continue
        p = np.concatenate([t.reshape(-1, 3), np.ones((t.size // 3, 1))], 1) @ mat   # row vectors, translation in row 3
        t = p[:, :3].reshape(-1, 3, 3)
        label = ("FH1" if rel in fh1 else "donor") if fh1 is not None and "--donor-only" not in argv else rel.split("/")[-1][:-9]
        if label not in legend:
            legend.append(label)
        T.append(t)
        M.append(np.full(len(t), legend.index(label)))
    T, M = np.concatenate(T), np.concatenate(M)
    for v in views:
        render.png("%s_%s.png" % (prefix, v), render.render(T, M, v, 1100))
    for k, l in enumerate(legend):
        print("%-3d %s %s" % (k, render.PALETTE[k % len(render.PALETTE)], l))
    print("%d triangles" % len(T))


if __name__ == "__main__":
    main(sys.argv[1:])
