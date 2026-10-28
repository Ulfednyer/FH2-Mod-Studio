"""Vectorized drop-in for fh3port/zfight.fix_model (same decisions, same output). Test: zfight_fast.py test <zip>..."""
import struct
import sys
import zipfile

import numpy as np

sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom
import zfight as Z

NEAR, SHARE, PUSH, LAYER_NEAR, LAYER_SHARE = Z.NEAR, Z.SHARE, Z.PUSH, Z.LAYER_NEAR, Z.LAYER_SHARE
REACH = 0.02          # nearest-centroid distance limit used by the original loop
CHUNK = 1 << 22       # elements per distance-matrix chunk


CELL = REACH * 1.01  # grid cell >= REACH: any centroid within REACH lies in one of the 27 neighbouring cells
OFFSETS = np.array([(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)], np.int64)


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
    pc = _cells(ca[rows])
    pid, cid = [], []
    for off in OFFSETS:
        kk = _key(pc + off)
        a = np.searchsorted(skeys, kk, "left")
        b = np.searchsorted(skeys, kk, "right")
        cnt = b - a
        tot = int(cnt.sum())
        if not tot:
            continue
        rep = np.repeat(np.arange(len(rows)), cnt)
        start = np.repeat(a - np.concatenate(([0], np.cumsum(cnt)[:-1])), cnt)
        pid.append(rep)
        cid.append(order[start + np.arange(tot)])
    if not pid:
        return 0, mask, k_all
    pid = np.concatenate(pid)
    cid = np.concatenate(cid)
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


def fix_model(d):
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
        g = Z._mesh_geometry(ents, e, bufs, ibs)
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
    if not changed:
        return d, log
    for bid in changed:
        e = bufs[bid]
        cnt = struct.unpack_from("<I", e.data, 0)[0]
        e.data = e.data[:16] + pos[bid].astype("<f4").tobytes() + e.data[16 + cnt * 12:]
    return geom.write_bundle(d, hsize, ents), log


if __name__ == "__main__" and sys.argv[1:2] == ["test"]:
    import time
    for zp in sys.argv[2:]:
        z = zipfile.ZipFile(zp)
        t_old = t_new = 0.0
        diff = same = 0
        for n in z.namelist():
            if not n.lower().endswith(".modelbin"):
                continue
            d = z.read(n)
            t = time.perf_counter(); a, la = Z.fix_model(d); t_old += time.perf_counter() - t
            t = time.perf_counter(); b, lb = fix_model(d); t_new += time.perf_counter() - t
            if a == b and la == lb:
                same += 1
            else:
                diff += 1
                print("  DIFF", n, len(la), len(lb), [x for x in la if x not in lb][:2], [x for x in lb if x not in la][:2])
        print("%s: identical %d, different %d, old %.1fs, new %.1fs" % (zp.split("/")[-1], same, diff, t_old, t_new))
