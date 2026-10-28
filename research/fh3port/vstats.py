"""Decode every drawn mesh's vertex channels (FH2 format) and print sanity stats per mesh:
normal / tangent length, |n.t|, UV transform block (Mesh >= 1.5: 80 bytes) and transformed UV ranges per channel.
usage: vstats.py <car.zip> <model-substring> [lodbit]"""
import zipfile, struct, sys, os
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix, geom
from matidump import s7

SIZE = vlayfix.SIZE


def mesh_tail80(data, ver):
    m = geom.parse_mesh(data, ver)
    return np.frombuffer(data[m["end"] - 80:m["end"]], "<f4").reshape(5, 4) if ver >= (1, 5) else None


def run(zp, key, lodbit):
    z = zipfile.ZipFile(zp)
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or key not in n.lower():
            continue
        bl = bundle.parse(z.read(n))
        vls = [vlayfix.parse_vlay(b.data)[0] for b in bl if b.tag == b"yaLV"]
        vbs = {vlayfix._id(b): b for b in bl if b.tag == b"BreV"}
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
        print("=====", n)
        for b in bl:
            if b.tag != b"hseM":
                continue
            mid, bone, flags, last, first, bucket, order = struct.unpack_from("<hhHBBHB", b.data, 0)
            if mid < 0 or not flags & lodbit:
                continue
            m, lid = vlayfix._mesh_layout(b.data, b.ver)
            els = vls[lid]
            ib = ibs.get(m["index_buffer"])
            cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
            idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
            idx = np.unique(idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"])
            ch = {}
            for bid, slot, stride, off in m["bindings"]:
                vb = vbs.get(bid)
                if vb is None or not stride:
                    continue
                vc = struct.unpack_from("<I", vb.data, 0)[0]
                rows = np.frombuffer(vb.data[16:16 + vc * stride], np.uint8).reshape(vc, stride)
                v = idx + off // stride
                v = v[(v >= 0) & (v < vc)]
                o = 0
                for el in [e for e in els if e["slot"] == slot]:
                    s = SIZE[el["fmt"]]
                    raw = rows[v, o:o + s].copy()
                    o += s
                    if el["fmt"] == 10:
                        ch[(el["sem"], el["idx"])] = raw.view("<f2").astype(np.float64).reshape(-1, 4)
                    elif el["fmt"] == 35:
                        ch[(el["sem"], el["idx"])] = raw.view("<u2").astype(np.float64).reshape(-1, 2) / 65535.0
                    elif el["fmt"] == 6:
                        ch[(el["sem"], el["idx"])] = raw.view("<f4").astype(np.float64).reshape(-1, 3)
            t80 = mesh_tail80(b.data, b.ver)
            line = "  %-30s n=%5d" % (mats.get(mid, "?")[:30], len(idx))
            nrm = ch.get(("NORMAL", 0))
            if nrm is not None:
                nl = np.linalg.norm(nrm[:, :3], axis=1)
                line += " |N| %.2f..%.2f" % (nl.min(), nl.max())
            for j in range(2):
                t = ch.get(("TANGENT", j))
                if t is not None:
                    tl = np.linalg.norm(t[:, :3], axis=1)
                    line += " |T%d| %.2f..%.2f w%+.0f/%+.0f" % (j, tl.min(), tl.max(), t[:, 3].min(), t[:, 3].max())
                    if nrm is not None:
                        line += " N.T%d %.2f" % (j, np.abs((t[:, :3] * nrm[:, :3]).sum(1)).mean())
            print(line)
            for i in range(5):
                uv = ch.get(("TEXCOORD", i))
                if uv is None:
                    continue
                sc = t80[i] if t80 is not None else np.array([1, 1, 0, 0])
                u = uv * sc[:2] + sc[2:]   # guess: scale.xy, offset.xy
                print("      T%d xf %s raw %.3f..%.3f/%.3f..%.3f -> %.2f..%.2f/%.2f..%.2f" % (
                    i, np.round(sc, 3), uv[:, 0].min(), uv[:, 0].max(), uv[:, 1].min(), uv[:, 1].max(),
                    u[:, 0].min(), u[:, 0].max(), u[:, 1].min(), u[:, 1].max()))


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2].lower(), int(sys.argv[3], 0) if len(sys.argv) > 3 else 2)
