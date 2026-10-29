"""Decodes every vertex buffer of a car zip's models through the layout its meshes use and reports values that make
FH2's shaders produce NaN: non-finite floats, zero-length NORMAL/TANGENT, |UV| huge. Only float formats are decoded
(dxgi 6 RGB32F, 2 RGBA32F, 16 RG32F, 10 RGBA16F, 34 RG16F); packed formats are skipped.
    py vertcheck.py <car.zip> [name filter]"""
import os
import struct
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fh3port"))
import bundle
import geom
import vlayfix

DT = {6: ("<f4", 3), 2: ("<f4", 4), 16: ("<f4", 2), 10: ("<f2", 4), 34: ("<f2", 2)}
SIZE = {6: 12, 2: 16, 16: 8, 10: 8, 34: 4, 13: 8, 37: 4, 24: 4, 28: 4, 35: 4, 41: 4, 42: 4, 11: 8, 12: 8}


def bid(b):
    m = b.meta(b"  dI")
    return struct.unpack("<i", m[:4])[0] if m and len(m) >= 4 else None


def check_model(d):
    blobs = bundle.parse(d)
    vl = [vlayfix.parse_vlay(b.data)[0] for b in blobs if b.tag == b"yaLV"]
    verb = {bid(b): b for b in blobs if b.tag == b"BreV"}
    seen, out = set(), []
    for b in blobs:
        if b.tag != b"hseM":
            continue
        m = geom.parse_mesh(b.data, b.ver)
        lid = struct.unpack_from("<i", b.data, m["bind_off"] - 8)[0]
        if not 0 <= lid < len(vl):
            continue
        for buf_id, slot, stride, _ in m["bindings"]:
            if (buf_id, lid, slot) in seen or buf_id not in verb:
                continue
            seen.add((buf_id, lid, slot))
            vb = verb[buf_id]
            cnt = struct.unpack_from("<I", vb.data, 0)[0]
            raw = np.frombuffer(vb.data[16:16 + cnt * stride], np.uint8).reshape(cnt, stride)
            off = 0
            for el in vl[lid]:
                if el["slot"] != slot:
                    continue
                o = el["off"] if el["off"] >= 0 else off
                sz = SIZE.get(el["fmt"])
                if sz is None:
                    out.append("unknown fmt %d" % el["fmt"])
                    break
                off = o + sz
                if el["fmt"] not in DT:
                    continue
                dt, n = DT[el["fmt"]]
                v = raw[:, o:o + sz].copy().view(dt).astype(np.float64).reshape(cnt, n)
                name = "%s%d" % (el["sem"], el["idx"])
                bad = ~np.isfinite(v).all(1)
                if bad.any():
                    out.append("%s non-finite %d/%d" % (name, bad.sum(), cnt))
                if el["sem"] in ("NORMAL", "TANGENT"):
                    ln = np.linalg.norm(np.nan_to_num(v[:, :3]), axis=1)
                    z = ln < 1e-3
                    if z.any():
                        out.append("%s zero-length %d/%d" % (name, z.sum(), cnt))
                    far = np.abs(ln - 1) > 0.1
                    if far.any():
                        out.append("%s not unit %d/%d (len %.3g..%.3g)" % (name, far.sum(), cnt, ln.min(), ln.max()))
                if el["sem"] == "TEXCOORD":
                    big = np.abs(np.nan_to_num(v)).max(1) > 1000
                    if big.any():
                        out.append("%s |uv|>1000 %d/%d" % (name, big.sum(), cnt))
            if off != stride and all(e["fmt"] in SIZE for e in vl[lid] if e["slot"] == slot):
                out.append("layout %d slot %d covers %d bytes, buffer stride %d" % (lid, slot, off, stride))
    return out


def main(zp, flt=""):
    z = zipfile.ZipFile(zp)
    nbad = 0
    for n in z.namelist():
        if n.lower().endswith(".modelbin") and flt.lower() in n.lower():
            probs = check_model(z.read(n))
            if probs:
                nbad += 1
                print(n)
                for p in sorted(set(probs)):
                    print("   ", p)
    print("models with problems:", nbad)


if __name__ == "__main__":
    main(*sys.argv[1:])
