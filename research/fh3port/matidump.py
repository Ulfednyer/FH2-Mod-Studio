import zipfile, struct, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
FH3PORT = os.path.abspath(os.path.join(HERE, "..", "..", "fh3port"))
if FH3PORT not in sys.path:
    sys.path.insert(0, FH3PORT)

import mtpr
def s7(d, p):
    n = s = 0
    while True:
        c = d[p]; p += 1; n |= (c & 0x7f) << s; s += 7
        if not c & 0x80: return d[p:p+n].decode("latin1"), p + n
def params(b):
    out = []
    ps, _ = mtpr.parse_params(b, None)
    for start, end, maj, mn, h, typ in ps:
        q = start + 7 + (16 if maj >= 3 else 0)
        if typ == 6: v = s7(b, q)[0].split("\\")[-1]
        elif typ in (0, 1, 5, 9): v = tuple(round(x, 3) for x in struct.unpack_from("<4f", b, q))
        elif typ == 2: v = round(struct.unpack_from("<f", b, q)[0], 3)
        elif typ in (3, 4): v = struct.unpack_from("<i", b, q)[0]
        else: v = b[q:end].hex()[:16]
        out.append((hex(h), mtpr.NAMES.get(typ, typ), v))
    return out
def dump_bundle(d, indent=""):
    for tag, ver, ep, doff, size in mtpr.blobs(d):
        b = d[doff:doff+size]; t = tag[::-1].decode("latin1")
        if t == "MATI": print(indent + "MATI", s7(b, 0)[0])
        elif t == "MTPR":
            for x in params(b): print(indent + "   ", x)
        elif t == "MATL": print(indent + "MATL", s7(b, 0)[0])
        elif t == "MatI":
            print(indent + "-- MatI")
            dump_bundle(b, indent + "  ")
def model(zp, name, want=None):
    z = zipfile.ZipFile(zp); n = next(x for x in z.namelist() if x.lower().endswith(name.lower()))
    d = z.read(n)
    for tag, ver, ep, doff, size in mtpr.blobs(d):
        if tag[::-1] == b"MatI":
            b = d[doff:doff+size]
            txt = b.decode("latin1", "ignore")
            if want and want not in txt.lower(): continue
            print("-- MatI"); dump_bundle(b, "  ")
if __name__ == "__main__":
    model(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
