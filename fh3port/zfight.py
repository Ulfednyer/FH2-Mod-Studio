"""Push opaque meshes that lie on top of a transparent mesh slightly back (z-fighting in FH2).

FH3 models put some glass overlays practically on top of the part behind them - NSX taillight: LED element
(lights_ch1bump, opaque) and glass overlay (gls_ch1_custom, transparent) are 0.027 mm apart. FH2's depth buffer can't
separate them and the surface flickers. For every opaque mesh (bucket bit 0x01) of a model whose triangles lie within
NEAR of a transparent mesh's (bucket bit 0x04) triangles for at least SHARE of its area, the opaque mesh's vertices
are moved PUSH metres against the glass normal (separates the surfaces; normally behind the glass). Only vertices used by that mesh alone are moved;
meshes sharing vertices with others are reported and left alone. Positions must be FH2 float32 (run after geom).

Nearest-triangle search uses a 2 cm grid (27 neighbour cells); it gives byte-identical results to the original
per-triangle loop (kept as research/fh3port/zfight_loop_reference.py) and is 5-9x faster (NSX 17.8 s -> 3.3 s).
"""
import struct
import zipfile

import numpy as np

import geom
import ziputil

NEAR = 0.0003     # 0.3 mm
SHARE = 0.5
PUSH = 0.001      # 1 mm
LAYER_NEAR = 0.0005   # 0.5 mm
LAYER_SHARE = 0.2
LOCAL_MIN = 8         # local pass: at least this many coplanar triangles
LOCAL_COS = 0.9       # ... facing the same way as the triangle they lie on (cos of the angle)
DECAL_NEAR = 0.0005   # decal pass: sticker triangles within 0.5 mm of an opaque surface ...
DECAL_PUSH = 0.001    # ... move 1 mm out (FH2's own overlays sit 0.5-2 mm above the body; FH3's S1 #2 0.2-0.5 mm)


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


REACH = 0.02          # a triangle counts only if the nearest centroid of the other mesh is this close
CELL = REACH * 1.01  # grid cell >= REACH: any centroid within REACH lies in one of the 27 neighbouring cells
OFFSETS = np.array([(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)], np.int64)
# _key(c + offset) == _key(c) + DELTA[offset]: each field has 21 bits and cells never reach the field limits
DELTA = OFFSETS[:, 0] * (1 << 42) + OFFSETS[:, 1] * (1 << 21) + OFFSETS[:, 2]


def _cells(pts):
    return np.floor(pts.astype(np.float64) / CELL).astype(np.int64)


def _key(c):
    return ((c[:, 0] + (1 << 20)) << 42) | ((c[:, 1] + (1 << 20)) << 21) | (c[:, 2] + (1 << 20))


def _near(ca, other, tol):
    """For each point of ca: the nearest centroid of `other` (lowest index on ties, like np.argmin) if one lies
    within REACH; counts points within REACH of it and within tol of its triangle's plane. Returns (count, mask, k).
    Exact: a centroid within REACH is always in the 27 cells around the point, and a point whose nearest centroid is
    farther than REACH never counts."""
    cg, g0, ng, lo, hi, order, skeys = other
    n = len(ca)
    mask = np.zeros(n, bool)
    k_all = np.zeros(n, np.int64)
    if n == 0 or len(cg) == 0:
        return 0, mask, k_all
    inside = np.all((ca >= lo - REACH) & (ca <= hi + REACH), axis=1)
    rows = np.nonzero(inside)[0]
    if not len(rows):
        return 0, mask, k_all
    # all 27 neighbour cells of every point in one search (was a Python loop of 27 x 2 searches per call: most of
    # the stage's time went to call overhead on small arrays); candidate order differs, the lexsort below fixes it
    kk = (_key(_cells(ca[rows]))[:, None] + DELTA[None, :]).ravel()
    a = np.searchsorted(skeys, kk, "left")
    cnt = np.searchsorted(skeys, kk, "right") - a
    tot = int(cnt.sum())
    if not tot:
        return 0, mask, k_all
    pid = np.repeat(np.arange(len(kk)) // len(DELTA), cnt)
    cid = order[np.repeat(a - (np.cumsum(cnt) - cnt), cnt) + np.arange(tot)]
    p = ca[rows][pid]
    d2 = ((cg[cid] - p) ** 2).sum(1)
    srt = np.lexsort((cid, d2, pid))          # per point: smallest distance, then lowest index (np.argmin rule)
    pid, cid = pid[srt], cid[srt]
    first = np.ones(len(pid), bool)
    first[1:] = pid[1:] != pid[:-1]
    r_local, k = pid[first], cid[first]
    pts = ca[rows][r_local]
    dist = np.linalg.norm(cg[k] - pts, axis=1)
    plane = np.abs(np.einsum("ij,ij->i", pts - g0[k], ng[k]))
    r = rows[r_local]
    mask[r] = (dist < REACH) & (plane < tol)
    k_all[r] = k
    return int(mask.sum()), mask, k_all


def _geom_of(T):
    cg = T.mean(1)
    ng = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    ng /= np.linalg.norm(ng, axis=1, keepdims=True) + 1e-12
    keys = _key(_cells(cg))
    order = np.argsort(keys, kind="stable")
    return cg, T[:, 0], ng, cg.min(0), cg.max(0), order, keys[order]


def is_decal(bucket):
    """Render-pass bits: 0x01 opaque, 0x04 transparent; stickers/livery overlays (ATST materials) use 0x38."""
    return not bucket & 0x05


def opaque_geometry(d):
    """[(lod flags, triangles)] of a model's opaque meshes, for the decal pass of its sibling models."""
    try:
        hsize, ents = geom.read_bundle(d)
    except geom.GeomError:
        return []
    bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
    ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
    out = []
    for e in ents:
        if e.tag != "Mesh":
            continue
        flags, last, first, bucket = struct.unpack_from("<HBBH", e.data, 4)
        if not flags & 0x7E or not bucket & 0x01 or bucket & 0x04 or struct.unpack_from("<h", e.data, 0)[0] < 0:
            continue
        g = _mesh_geometry(ents, e, bufs, ibs)
        if g:
            cnt = struct.unpack_from("<I", bufs[g[0]].data, 0)[0]
            pts = np.frombuffer(bufs[g[0]].data[16:16 + cnt * 12], "<f4").reshape(-1, 3)
            out.append((flags, pts[g[1]].astype(np.float64)))
    return out


def fix_model(d, siblings=()):
    """siblings: opaque_geometry() of the other models of the same part (sticker overlays live in their own
    modelbin next to the part they lie on: hoodLivery_a over hood_a)."""
    hsize, ents = geom.read_bundle(d)
    bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
    ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
    meshes = []
    for i, e in enumerate(ents):
        if e.tag != "Mesh":
            continue
        flags, last, first, bucket = struct.unpack_from("<HBBH", e.data, 4)
        if not flags & 0x7E:
            continue
        if struct.unpack_from("<h", e.data, 0)[0] < 0:
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
    # how many meshes use each vertex (only "used by more than one mesh" matters)
    shared = {}
    for bid in pos:
        count = np.zeros(len(pos[bid]), np.int32)
        for i, bucket, flags, b, idx in meshes:
            if b == bid:
                count[np.unique(idx)] += 1
        shared[bid] = count > 1
    cache = {}

    def geo(m):
        if m[0] not in cache:
            cache[m[0]] = _geom_of(pos[m[3]][m[4]])
        return cache[m[0]]

    log, changed, moved = [], set(), set()
    glass = [m for m in meshes if m[1] & 0x04]
    for m in meshes:
        i, bucket, flags, bid, idx = m
        if not bucket & 0x01 or bucket & 0x04:
            continue
        ca = pos[bid][idx].mean(1)
        best = None
        for g in glass:
            if not (g[2] & flags & 0x7E):
                continue
            near, mask, k = _near(ca, geo(g), NEAR)
            if near >= SHARE * len(ca) and (best is None or near > best[0]):
                best = (near, g[0], geo(g)[2][k[mask]].mean(0))
        if not best:
            continue
        verts = np.unique(idx)
        if shared[bid][verts].any():
            log.append("mesh %d on glass mesh %d: shares vertices, left alone" % (i, best[1]))
            continue
        n = best[2] / (np.linalg.norm(best[2]) + 1e-12)
        pos[bid][verts] -= (PUSH * n).astype(np.float32)
        cache.pop(i, None)
        changed.add(bid)
        moved.add(i)
        log.append("mesh %d moved %.1f mm off glass mesh %d (%d of %d triangles coplanar)" % (i, PUSH * 1000, best[1], best[0], len(ca)))
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
            near, mask, k = _near(ca, geo(b), LAYER_NEAR)
            if near < LAYER_SHARE * len(ca):
                continue
            verts = np.unique(idx)
            if shared[bid][verts].any():
                log.append("mesh %d on mesh %d: shares vertices, left alone" % (i, b[0]))
                break
            na = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]).sum(0)
            na /= np.linalg.norm(na) + 1e-12
            pos[bid][verts] += (PUSH * na).astype(np.float32)
            cache.pop(i, None)
            changed.add(bid)
            moved.add(i)
            log.append("mesh %d moved %.1f mm in front of mesh %d (%d of %d triangles within %.1f mm)" % (
                i, PUSH * 1000, b[0], near, len(ca), LAYER_NEAR * 1000))
            break
    # local overlaps: a strip of a bigger part lying on another (Alumi Craft side paint on the chassis: 181 of 3,936
    # triangles within 0.5 mm, too few for the whole-mesh rule, and its average normal is ~0 because it wraps both
    # sides). Only the vertices of the smaller mesh's triangles that lie within LAYER_NEAR of the other mesh AND face
    # the same way (coplanar, not crossing) move PUSH out along their own vertex normals.
    for a in sorted(opaque, key=lambda m: len(m[4])):
        i, bucket, flags, bid, idx = a
        if i in moved:
            continue
        T = pos[bid][idx]
        ca = T.mean(1)
        fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        hit = np.zeros(len(idx), bool)
        others = []
        for b in opaque:
            if b[0] == i or len(b[4]) < len(idx) or not (b[2] & flags & 0x7E):
                continue
            near, mask, k = _near(ca, geo(b), LAYER_NEAR)
            if not near:
                continue
            ng = geo(b)[2]
            unit = fn[mask] / (np.linalg.norm(fn[mask], axis=1, keepdims=True) + 1e-12)
            same = np.einsum("ij,ij->i", unit, ng[k[mask]]) > LOCAL_COS
            sel = np.nonzero(mask)[0][same]
            if len(sel):
                hit[sel] = True
                others.append(b[0])
        if hit.sum() < LOCAL_MIN:
            continue
        verts = np.unique(idx[hit])
        verts = verts[~shared[bid][verts]]
        if not len(verts):
            log.append("mesh %d: %d coplanar triangles on mesh(es) %s, vertices shared, left alone" % (i, hit.sum(), others))
            continue
        vn = np.zeros((len(pos[bid]), 3))
        for c in range(3):
            np.add.at(vn, idx[:, c], fn)
        n = vn[verts] / (np.linalg.norm(vn[verts], axis=1, keepdims=True) + 1e-12)
        pos[bid][verts] += (PUSH * n).astype(np.float32)
        cache.pop(i, None)
        changed.add(bid)
        moved.add(i)
        log.append("mesh %d: %d of %d triangles coplanar with mesh(es) %s within %.1f mm, %d vertices moved %.1f mm out" % (
            i, hit.sum(), len(idx), others, LAYER_NEAR * 1000, len(verts), PUSH * 1000))
    # decals: sticker / livery overlay meshes (render pass 0x38, alpha-tested) lying on an opaque surface of this model
    # or of a sibling model. FH3 keeps them 0.2-0.5 mm above the body, closer than FH2's depth buffer separates (S1 #2:
    # black sticker sheets flickering through the paint). Their triangles within DECAL_NEAR of an opaque triangle
    # facing the same way move DECAL_PUSH out along their own vertex normals.
    others = [(m[2], None, m) for m in opaque] + [(f, _geom_of(T), None) for f, T in siblings]
    for a in meshes:
        i, bucket, flags, bid, idx = a
        if not is_decal(bucket) or i in moved:
            continue
        T = pos[bid][idx]
        ca = T.mean(1)
        fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        unit = fn / (np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12)
        hit = np.zeros(len(idx), bool)
        for f, g, m in others:
            if not (f & flags & 0x7E):
                continue
            g = g if g is not None else geo(m)
            near, mask, k = _near(ca, g, DECAL_NEAR)
            if near:
                same = np.einsum("ij,ij->i", unit[mask], g[2][k[mask]]) > LOCAL_COS
                hit[np.nonzero(mask)[0][same]] = True
        if not hit.any():
            continue
        verts = np.unique(idx[hit])
        own = np.zeros(len(pos[bid]), bool)            # vertices used only by decal meshes may move
        for m in meshes:
            if m[3] == bid and not is_decal(m[1]):
                own[np.unique(m[4])] = True
        verts = verts[~own[verts]]
        if not len(verts):
            continue
        vn = np.zeros((len(pos[bid]), 3))
        for c in range(3):
            np.add.at(vn, idx[:, c], fn)
        n = vn[verts] / (np.linalg.norm(vn[verts], axis=1, keepdims=True) + 1e-12)
        pos[bid][verts] += (DECAL_PUSH * n).astype(np.float32)
        changed.add(bid)
        moved.add(i)
        log.append("decal mesh %d: %d of %d triangles within %.1f mm of the paint, %d vertices moved %.1f mm out" % (
            i, hit.sum(), len(idx), DECAL_NEAR * 1000, len(verts), DECAL_PUSH * 1000))
    if not changed:
        return d, log
    for bid in changed:
        e = bufs[bid]
        cnt = struct.unpack_from("<I", e.data, 0)[0]
        e.data = e.data[:16] + pos[bid].astype("<f4").tobytes() + e.data[16 + cnt * 12:]
    return geom.write_bundle(d, hsize, ents), log


def fix_zip(src, dst):
    log = []
    with zipfile.ZipFile(src) as zin, ziputil.writer(dst) as zout:
        # opaque geometry per part folder, for models whose decals lie on a sibling model
        folders = {}
        for n in zin.namelist():
            if n.lower().endswith(".modelbin") and "livery" in n.lower():
                folders.setdefault(n.rsplit("/", 1)[0].lower(), None)
        sib = {}
        for n in zin.namelist():
            folder = n.rsplit("/", 1)[0].lower()
            if n.lower().endswith(".modelbin") and folder in folders and "livery" not in n.lower():
                sib.setdefault(folder, []).extend(opaque_geometry(zin.read(n)))
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".modelbin"):
                folder = info.filename.rsplit("/", 1)[0].lower()
                siblings = sib.get(folder, []) if "livery" in info.filename.lower() else []
                data, l = fix_model(data, siblings)
                log += ["%s: %s" % (info.filename.split("/")[-1], x) for x in l]
            zout.writestr(info.filename, data)
    return log
