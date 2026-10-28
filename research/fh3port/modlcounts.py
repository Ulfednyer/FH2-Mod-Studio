"""Check Modl header counts (mesh, VerB+IndB+MBuf+ConB+Skin, VLay, MatI) against the blobs in every modelbin of a car zip."""
import zipfile, struct, sys, collections, os

HERE = os.path.dirname(os.path.abspath(__file__))
FH3PORT = os.path.abspath(os.path.join(HERE, "..", "..", "fh3port"))
if FH3PORT not in sys.path:
    sys.path.insert(0, FH3PORT)

import bundle
for zp in sys.argv[1:]:
    z = zipfile.ZipFile(zp); bad = n = 0
    for nm in z.namelist():
        if not nm.lower().endswith(".modelbin"): continue
        bl = bundle.parse(z.read(nm)); c = collections.Counter(b.tag[::-1].decode("latin1") for b in bl)
        modl = next((b for b in bl if b.tag == b"ldoM"), None)
        if modl is None: continue
        h = struct.unpack_from("<HHHH", modl.data, 0); n += 1
        if h != (c["Mesh"], c["VerB"] + c["IndB"] + c["MBuf"] + c["ConB"] + c["Skin"], c["VLay"], c["MatI"]):
            bad += 1; print("  MISMATCH", nm, h, dict(c))
    print(zp, "models", n, "Modl count mismatches", bad)
