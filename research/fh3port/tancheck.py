"""Stored TANGENTj vs the tangent computed from positions + TEXCOORDk (dP/du per triangle, accumulated per vertex).
Prints, per mesh and (j, k) pair, the mean |cos| of the angle and the share of vertices whose bitangent sign agrees
with the stored w. FH2 data tells which UV channel each tangent belongs to and what "correct" looks like.
usage: tancheck.py <car.zip> <model-substring,...> [lodbit]"""
import zipfile, struct, sys, collections
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix, geom
from matidump import s7

SIZE = vlayfix.SIZE


def chans(bl, m, els):
    vbs = {vlayfix._id(b): b for b in bl if b.tag == b"BreV"}
    out = {}
    for bid, slot, stride, off in m["bindings"]:
        vb = vbs.get(bid)
        if vb is None or not stride:
            continue
        vc = struct.unpack_from("<I", vb.data, 0)[0]
        rows = np.frombuffer(vb.data[16:16 + vc * stride], np.uint8).reshape(vc, stride)
        o = 0
        for el in [e for e in els if e["slot"] == slot]:
            s = SIZE[el["fmt"]]
            raw = rows[:, o:o + s].copy()
            o += s
            key = (el["sem"], el["idx"])
            if el["fmt"] == 6:
                out[key] = (raw.view("<f4").astype(np.float64).reshape(-1, 3), off // stride)
            elif el["fmt"] == 10:
                out[key] = (raw.view("<f2").astype(np.float64).reshape(-1, 4), off // stride)
            elif el["fmt"] == 35:
                out[key] = (raw.view("<u2").astype(np.float64).reshape(-1, 2) / 65535.0, off // stride)
    return out


def run(zp, keys, lodbit):
    z = zipfile.ZipFile(zp)
    agg = collections.defaultdict(list)
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not any(k in n.lower() for k in keys):
            continue
        bl = bundle.parse(z.read(n))
        vls = [vlayfix.parse_vlay(b.data)[0] for b in bl if b.tag == b"yaLV"]
        ibs = {vlayfix._id(b): b for b in bl if b.tag == b"BdnI"}
        for b in bl:
            if b.tag != b"hseM":
                continue
            mid = struct.unpack_from("<h", b.data, 0)[0]
            flags = struct.unpack_from("<H", b.data, 4)[0]
            if mid < 0 or not flags & lodbit:
                continue
            m, lid = vlayfix._mesh_layout(b.data, b.ver)
            xf = np.frombuffer(b.data[m["end"] - 80:m["end"]], "<f4").reshape(5, 4)
            ch = chans(bl, m, vls[lid])
            if ("POSITION", 0) not in ch:
                continue
            ib = ibs[m["index_buffer"]]
            cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
            idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
            idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"]
            idx = idx[:len(idx) // 3 * 3].reshape(-1, 3)
            P, po = ch[("POSITION", 0)]
            N, no = ch[("NORMAL", 0)]
            for j in range(5):
                if ("TANGENT", j) not in ch:
                    continue
                T, to = ch[("TANGENT", j)]
                for k in range(4):
                    if ("TEXCOORD", k) not in ch:
                        continue
                    U, uo = ch[("TEXCOORD", k)]
                    # UV transform: offset.x, scale.x, offset.y, scale.y
                    U = np.column_stack([U[:, 0] * xf[k, 1] + xf[k, 0], U[:, 1] * xf[k, 3] + xf[k, 2]])
                    pi, ui, ti, ni = idx + po, idx + uo, idx + to, idx + no
                    ok = (pi < len(P)).all(1) & (ui < len(U)).all(1) & (ti < len(T)).all(1) & (ni < len(N)).all(1)
                    pi, ui, ti, ni = pi[ok], ui[ok], ti[ok], ni[ok]
                    p0, p1, p2 = P[pi[:, 0]], P[pi[:, 1]], P[pi[:, 2]]
                    u0, u1, u2 = U[ui[:, 0]], U[ui[:, 1]], U[ui[:, 2]]
                    e1, e2 = p1 - p0, p2 - p0
                    d1, d2 = u1 - u0, u2 - u0
                    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
                    good = np.abs(det) > 1e-12
                    if good.sum() < 3:
                        continue
                    r = 1.0 / det[good]
                    tg = (e1[good] * d2[good, 1:2] - e2[good] * d1[good, 1:2]) * r[:, None]
                    bt = (e2[good] * d1[good, 0:1] - e1[good] * d2[good, 0:1]) * r[:, None]
                    # compare per triangle corner 0
                    Ts = T[ti[good, 0]]
                    Ns = N[ni[good, 0], :3]
                    tgn = tg / (np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12)
                    cos = (tgn * Ts[:, :3]).sum(1)
                    hand = np.sign((np.cross(Ns, tg) * bt).sum(1))
                    agree = (hand == np.sign(Ts[:, 3])).mean()
                    agg[(j, k)].append((np.abs(cos).mean(), (cos > 0).mean(), agree, good.sum()))
    for (j, k), v in sorted(agg.items()):
        a = np.array(v)
        w = a[:, 3]
        print("  TANGENT%d vs TEXCOORD%d: |cos| %.2f  cos>0 %.2f  w agrees %.2f  (meshes %d)" % (
            j, k, (a[:, 0] * w).sum() / w.sum(), (a[:, 1] * w).sum() / w.sum(), (a[:, 2] * w).sum() / w.sum(), len(v)))


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2].lower().split(","), int(sys.argv[3], 0) if len(sys.argv) > 3 else 2)
