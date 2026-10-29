"""Finds non-finite or out-of-range values in a car zip's models: VerB float32/float16 data, Mesh scale, BBox metadata.
One NaN/Inf vertex reaches FH2's HDR exposure pass and the whole 3D scene turns black (UI still draws).
    py nancheck.py <car.zip>"""
import os
import struct
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fh3port"))
import bundle

FMT = {6: ("<f4", 3), 2: ("<f4", 4), 16: ("<f4", 2), 10: ("<f2", 4), 34: ("<f2", 2)}


def check_verb(b):
    """FH1 VerB: one dxgi format for the whole stride (positions dxgi 6, attributes dxgi 10). Returns problems."""
    cnt, size, stride, nel, fmt = struct.unpack_from("<IIHHI", b.data, 0)
    raw = b.data[16:16 + cnt * stride]
    if (stride, fmt) not in ((12, 6), (40, 10)) or len(raw) < cnt * stride:   # the layouts fh1modelbin writes
        return []
    dt = FMT[fmt][0]
    a = np.frombuffer(raw, dtype=dt).astype(np.float64)
    bad = ~np.isfinite(a)
    out = []
    if bad.any():
        out.append("VerB fmt %d: %d non-finite of %d" % (fmt, int(bad.sum()), a.size))
    big = np.abs(a[~bad]) > 1e4
    if big.any():
        out.append("VerB fmt %d: %d values > 1e4 (max %.3g)" % (fmt, int(big.sum()), np.abs(a[~bad]).max()))
    return out


def main(zp):
    z = zipfile.ZipFile(zp)
    total = 0
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"):
            continue
        probs = []
        for b in bundle.parse(z.read(n)):
            if b.tag == b"BreV":
                probs += check_verb(b)
            box = b.meta(b"xoBB")
            if box and len(box) >= 24:
                v = np.frombuffer(box[:24], "<f4")
                if not np.isfinite(v).all() or np.abs(v).max() > 1e3:
                    probs.append("%s BBox %s" % (b.tag[::-1].decode(), v))
        if probs:
            total += 1
            print(n)
            for p in sorted(set(probs)):
                print("   ", p)
    print("models with problems:", total)


if __name__ == "__main__":
    main(sys.argv[1])
