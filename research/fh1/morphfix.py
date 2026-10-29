"""Clears the Mesh morph bytes (file offsets 12, 13 = FH2 mesh +0x12C, +0x12D) in every model of an installed car zip
that has no Mrph blob. FH2's Model_LoadFromBundle opens the Mrph blob unchecked when any mesh sets the flag; the
first fh1modelbin wrote 1 there -> Autoshow crash game+0x13e7398 (Blob_OpenDataStream on a NULL blob).

    py morphfix.py <installed car zip>      (FH2 must be closed; the original zip is kept by the porter journal)
"""
import os
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "..", "fh3port")))
import bundle
import fh3port


def fix_model(d):
    blobs = bundle.parse(d)
    if any(b.tag == b"hprM" for b in blobs):
        return None
    hit = False
    for b in blobs:
        if b.tag == b"hseM" and b.ver >= (1, 3) and (b.data[12] or b.data[13]):
            md = bytearray(b.data)
            md[12] = md[13] = 0
            b.data = bytes(md)
            hit = True
    return bundle.serialize(blobs) if hit else None


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
