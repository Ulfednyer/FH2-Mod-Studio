"""Push opaque meshes that lie on top of a transparent mesh slightly back (z-fighting in FH2).

FH3 models put some glass overlays practically on top of the part behind them - NSX taillight: LED element
(lights_ch1bump, opaque) and glass overlay (gls_ch1_custom, transparent) are 0.027 mm apart. FH2's depth buffer can't
separate them and the surface flickers. For every opaque mesh (bucket bit 0x01) of a model whose triangles lie within
NEAR of a transparent mesh's (bucket bit 0x04) triangles for at least SHARE of its area, the opaque mesh's vertices
are moved PUSH metres against the glass normal (separates the surfaces; normally behind the glass). Only vertices used by that mesh alone are moved;
meshes sharing vertices with others are reported and left alone. Positions must be FH2 float32 (run after geom).
"""
import struct
import zipfile

import numpy as np

import geom

NEAR = 0.0003     # 0.3 mm
SHARE = 0.5
PUSH = 0.001      # 1 mm
LAYER_NEAR = 0.0005   # 0.5 mm
LAYER_SHARE = 0.2


def _mesh_geometry(ents, e, bufs, ibs):
    m = geom.parse_mesh(e.data, e.ver)
    for bid, slot, stride, off in m["bindings"]:
        b = bufs.get(bid)
        if b is None:
            continue
        cnt, sz, st, nel, fmt = struct.unpack_from("<IIHHI", b.data, 0)
        if fmt == 6 and st == 12 and stride:
            ib = ibs.get(m["index_buffer"])
            if ib is None:
                return None
            icnt, isz, ist = struct.unpack_from("<IIH", ib.data, 0)
            idx = np.frombuffer(ib.data[16:16 + icnt * ist], "<u4" if ist == 4 else "<u2").astype(np.int64)
            idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"] + off // stride
            idx = idx[: len(idx) // 3 * 3].reshape(-1, 3)
            if len(idx) == 0 or idx.max() >= cnt:
                return None
            return bid, idx
    return None


def fix_model(d):
    hsize, ents = geom.read_bundle(d)
    bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
    ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
    meshes = []
    for i, e in enumerate(ents):
        if e.tag != "Mesh":
            continue
        flags, last, first, bucket = struct.unpack_from("<HBBH", e.data, 4)
        if not flags & 0x7E:          # not drawn at LOD0..5
            continue
        if struct.unpack_from("<h", e.data, 0)[0] < 0:   # shadow-caster copy (no material): follows its mesh
            continue
        g = _mesh_geometry(ents, e, bufs, ibs)
        if g:
            meshes.append((i, bucket, flags, g[0], g[1]))
    if not meshes:
        return d, []
    pos = {}
    for bid in {m[3] for m in meshes}:
        cnt = struct.unpack_from("<I", bufs[bid].data, 0)[0]
        pos[bid] = np.frombuffer(bufs[bid].data[16:16 + cnt * 12], "<f4").reshape(-1, 3).copy()
    # vertex usage per buffer, to avoid moving vertices other visible meshes use (shadow-caster copies have no
    # material (id -1, bucket 0x9) and reuse the visible mesh's vertices - they may move along)
    users = {}
    for i, bucket, flags, bid, idx in meshes:
        for v in np.unique(idx):
            users.setdefault((bid, int(v)), set()).add(i)
    log, changed, moved = [], set(), set()
    glass = [m for m in meshes if m[1] & 0x04]
    for i, bucket, flags, bid, idx in meshes:
        if not bucket & 0x01 or bucket & 0x04:
            continue
        T = pos[bid][idx]
        ca = T.mean(1)
        best = None
        for gi, gb, gf, gbid, gidx in glass:
            if not (gf & flags & 0x7E):
                continue
            G = pos[gbid][gidx]
            cg = G.mean(1)
            ng = np.cross(G[:, 1] - G[:, 0], G[:, 2] - G[:, 0])
            ng /= np.linalg.norm(ng, axis=1, keepdims=True) + 1e-12
            near, normals = 0, []
            for p in ca:
                k = np.argmin(((cg - p) ** 2).sum(1))
                if np.linalg.norm(cg[k] - p) < 0.02 and abs(np.dot(p - G[k, 0], ng[k])) < NEAR:
                    near += 1
                    normals.append(ng[k])
            if near >= SHARE * len(ca) and (best is None or near > best[0]):
                best = (near, gi, np.mean(normals, 0))
        if not best:
            continue
        verts = np.unique(idx)
        if any(len(users[(bid, int(v))]) > 1 for v in verts):
            log.append("mesh %d on glass mesh %d: shares vertices, left alone" % (i, best[1]))
            continue
        n = best[2] / (np.linalg.norm(best[2]) + 1e-12)
        pos[bid][verts] -= (PUSH * n).astype(np.float32)
        changed.add(bid)
        moved.add(i)
        log.append("mesh %d moved %.1f mm off glass mesh %d (%d of %d triangles coplanar)" % (i, PUSH * 1000, best[1], best[0], len(ca)))
    # layered opaque parts: FH3 stacks light layers (e.g. NSX taillight tail/brake layers, 0.003-0.02 mm apart, also
    # at LOD1 = while driving) that FH3 blends; in FH2 both are opaque and fight. The smaller mesh moves PUSH along
    # its own face normal (in front of the other) when >= LAYER_SHARE of its triangles lie within LAYER_NEAR.
    opaque = [m for m in meshes if m[1] & 0x01 and not m[1] & 0x04]
    for a in sorted(opaque, key=lambda m: len(m[4])):
        i, bucket, flags, bid, idx = a
        if i in moved:
            continue
        T = pos[bid][idx]
        ca = T.mean(1)
        for b in opaque:
            if b[0] == i or len(b[4]) < len(idx) or not (b[2] & flags & 0x7E):
                continue
            G = pos[b[3]][b[4]]
            cg = G.mean(1)
            ng = np.cross(G[:, 1] - G[:, 0], G[:, 2] - G[:, 0])
            ng /= np.linalg.norm(ng, axis=1, keepdims=True) + 1e-12
            near = 0
            for p in ca:
                k = np.argmin(((cg - p) ** 2).sum(1))
                if np.linalg.norm(cg[k] - p) < 0.02 and abs(np.dot(p - G[k, 0], ng[k])) < LAYER_NEAR:
                    near += 1
            if near < LAYER_SHARE * len(ca):
                continue
            verts = np.unique(idx)
            if any(len(users[(bid, int(v))]) > 1 for v in verts):
                log.append("mesh %d on mesh %d: shares vertices, left alone" % (i, b[0]))
                break
            na = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]).sum(0)
            na /= np.linalg.norm(na) + 1e-12
            pos[bid][verts] += (PUSH * na).astype(np.float32)
            changed.add(bid)
            moved.add(i)
            log.append("mesh %d moved %.1f mm in front of mesh %d (%d of %d triangles within %.1f mm)" % (
                i, PUSH * 1000, b[0], near, len(ca), LAYER_NEAR * 1000))
            break
    if not changed:
        return d, log
    for bid in changed:
        e = bufs[bid]
        cnt = struct.unpack_from("<I", e.data, 0)[0]
        e.data = e.data[:16] + pos[bid].astype("<f4").tobytes() + e.data[16 + cnt * 12:]
    return geom.write_bundle(d, hsize, ents), log


def fix_zip(src, dst):
    log = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".modelbin"):
                data, l = fix_model(data)
                log += ["%s: %s" % (info.filename.split("/")[-1], x) for x in l]
            zout.writestr(info.filename, data)
    return log
