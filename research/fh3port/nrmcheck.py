"""Do vertex normals agree with the triangles? Per mesh: mean dot(vertex normal, face normal of its triangles) for
the first LOD, plus the share of triangles whose summed vertex normals point against the face (= flipped/garbage).
Winding sign is unknown, so both signs are shown; FH2 meshes should be ~+1 or ~-1 consistently.
usage: nrmcheck.py <car.zip> <model-substring,...> [lodbit]"""
import zipfile, struct, sys, collections
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix
from matidump import s7

SIZE = vlayfix.SIZE


def channels(bl, m, els):
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
            if el["fmt"] == 6:
                out[el["sem"]] = (raw.view("<f4").astype(np.float64).reshape(-1, 3), off // stride)
            elif el["fmt"] == 10 and el["sem"] == "NORMAL":
                out[el["sem"]] = (raw.view("<f2").astype(np.float64).reshape(-1, 4)[:, :3], off // stride)
    return out


def run(zp, keys, lodbit, quiet=False):
    z = zipfile.ZipFile(zp)
    tot = collections.Counter()
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not any(k in n.lower() for k in keys):
            continue
        bl = bundle.parse(z.read(n))
        vls = [vlayfix.parse_vlay(b.data)[0] for b in bl if b.tag == b"yaLV"]
        ibs = {vlayfix._id(b): b for b in bl if b.tag == b"BdnI"}
        mats = {}
        for b in bl:
            if b.tag == b"ItaM":
                try:
                    for ib in bundle.parse(b.data):
                        if ib.tag == b"ITAM":
                            mats[vlayfix._id(b)] = s7(ib.data, 0)[0].split("\\")[-1]
                except ValueError:
                    pass
        if not quiet:
            print("=====", n)
        for b in bl:
            if b.tag != b"hseM":
                continue
            mid = struct.unpack_from("<h", b.data, 0)[0]
            flags = struct.unpack_from("<H", b.data, 4)[0]
            if mid < 0 or not flags & lodbit:
                continue
            m, lid = vlayfix._mesh_layout(b.data, b.ver)
            ch = channels(bl, m, vls[lid])
            if "POSITION" not in ch or "NORMAL" not in ch:
                continue
            ib = ibs[m["index_buffer"]]
            cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
            idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
            idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"]
            idx = idx[:len(idx) // 3 * 3].reshape(-1, 3)
            P, po = ch["POSITION"]; N, no = ch["NORMAL"]
            pi, ni = idx + po, idx + no
            ok = (pi < len(P)).all(1) & (ni < len(N)).all(1)
            pi, ni = pi[ok], ni[ok]
            T = P[pi]
            fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
            area = np.linalg.norm(fn, axis=1)
            good = area > 1e-12
            fn = fn[good] / area[good, None]
            vn = N[ni[good]].sum(1)
            vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
            d = (fn * vn).sum(1)
            pos, neg = (d > 0.3).mean(), (d < -0.3).mean()
            key = "consistent" if max(pos, neg) > 0.9 else "MIXED"
            tot[("+" if pos >= neg else "-", key)] += 1
            if not quiet:
                print("  %-34s tris %5d  dot>0.3 %.2f  dot<-0.3 %.2f  %s" % (mats.get(mid, "?")[:34], len(d), pos, neg, key))
    return tot


if __name__ == "__main__":
    print(dict(run(sys.argv[1], sys.argv[2].lower().split(","), int(sys.argv[3], 0) if len(sys.argv) > 3 else 2,
                   quiet=len(sys.argv) > 4)))
