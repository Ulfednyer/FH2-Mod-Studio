"""Repairs FH1-converted models in an installed car zip whose TEXCOORDs hold half floats although the layout declares
R16G16_UNORM (dxgi 35), with all-zero UV transforms in the mesh tails (first fh1modelbin). FH2 computes
uv = offset + unorm * scale, so every UV was 0. Re-encodes the UVs as UNORM16 and writes per-channel transforms
(fh1modelbin.uv_transform) into every non-shadow mesh of the model.

    py uvfix.py <installed car zip>      (FH2 must be closed; the original zip is kept by the porter journal)
"""
import os
import struct
import sys
import zipfile

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "..", "fh3port")))
sys.path.insert(0, _HERE)
import bundle
import fh3port
import geom
import vlayfix
from fh1modelbin import encode_uv, uv_tail, uv_transform

SIZE = {6: 12, 2: 16, 16: 8, 10: 8, 34: 4, 35: 4}


def _id(b):
    m = b.meta(b"  dI")
    return struct.unpack("<i", m[:4])[0] if m and len(m) >= 4 else None


def fix_model(d):
    blobs = bundle.parse(d)
    layouts = [vlayfix.parse_vlay(b.data)[0] for b in blobs if b.tag == b"yaLV"]
    verbs = {_id(b): b for b in blobs if b.tag == b"BreV"}
    meshes = []
    for b in blobs:
        if b.tag != b"hseM" or b.ver < (1, 5) or struct.unpack_from("<h", b.data, 0)[0] < 0:
            continue
        m = geom.parse_mesh(b.data, b.ver)
        tail = struct.unpack_from("<20f", b.data, m["end"] - 80)
        meshes.append((b, m, struct.unpack_from("<i", b.data, m["bind_off"] - 8)[0], tail))
    # only the broken FH1 shape: every real mesh has zero scale on TEXCOORD0
    if not meshes or any(t[1] != 0 or t[3] != 0 for _, _, _, t in meshes):
        return None

    # TEXCOORD element offsets per (buffer, layout); all elements must be float16-sized float formats or dxgi 35
    uses = {}
    for b, m, lid, _ in meshes:
        for buf_id, slot, stride, _ in m["bindings"]:
            off, tcs = 0, {}
            for el in layouts[lid]:
                if el["slot"] != slot:
                    continue
                o = el["off"] if el["off"] >= 0 else off
                if el["fmt"] not in SIZE:
                    raise ValueError("unknown vertex format %d" % el["fmt"])
                off = o + SIZE[el["fmt"]]
                if el["sem"] == "TEXCOORD" and el["fmt"] == 35:
                    tcs[el["idx"]] = o
            if tcs:
                uses[buf_id] = (stride, tcs)

    # decode the half floats, one transform per TEXCOORD index over every buffer of the model
    decoded = {}
    for buf_id, (stride, tcs) in uses.items():
        vb = verbs[buf_id]
        cnt = struct.unpack_from("<I", vb.data, 0)[0]
        raw = np.frombuffer(vb.data[16:16 + cnt * stride], np.uint8).reshape(cnt, stride)
        for k, o in tcs.items():
            decoded[(buf_id, k)] = raw[:, o:o + 4].copy().view("<f2").astype(np.float64).reshape(cnt, 2)
    xfs = []
    for k in range(5):
        vals = [v for (bid, kk), v in decoded.items() if kk == k]
        xfs.append(uv_transform(np.concatenate(vals)) if vals else (np.zeros(2), np.ones(2)))
    if not all(np.isfinite(np.concatenate(v)).all() for v in xfs):
        raise ValueError("non-finite UVs")

    for buf_id, (stride, tcs) in uses.items():
        vb = verbs[buf_id]
        cnt = struct.unpack_from("<I", vb.data, 0)[0]
        data = bytearray(vb.data)
        raw = np.frombuffer(data, np.uint8, cnt * stride, 16).reshape(cnt, stride).copy()
        for k, o in tcs.items():
            raw[:, o:o + 4] = encode_uv(decoded[(buf_id, k)], xfs[k]).view(np.uint8).reshape(cnt, 4)
        data[16:16 + cnt * stride] = raw.tobytes()
        vb.data = bytes(data)
    tail = uv_tail(xfs)
    for b, m, _, _ in meshes:
        md = bytearray(b.data)
        md[m["end"] - 80:m["end"]] = tail
        b.data = bytes(md)
    return bundle.serialize(blobs)


def main(zp):
    with zipfile.ZipFile(zp) as z:
        fixed = {}
        for n in z.namelist():
            if n.lower().endswith(".modelbin"):
                out = fix_model(z.read(n))
                if out is not None:
                    fixed[n] = out
    if fixed:
        j = fh3port.journal()
        fh3port.replace_in_zip(j, zp, fixed)
        fh3port.save_journal(j)
    print("fixed %d models" % len(fixed))
    for n in sorted(fixed):
        print("  " + n)


if __name__ == "__main__":
    main(sys.argv[1])
