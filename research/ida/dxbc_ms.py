# Scans a binary for DXBC shader blobs and reports Texture2DMS bindings with their declared sample count (RDEF).
import struct, sys
from collections import Counter

data = open(sys.argv[1], "rb").read()
counts, names, shaders, ms_shaders = Counter(), Counter(), 0, 0
pos = data.find(b"DXBC")
while pos >= 0:
    try:
        total, nchunks = struct.unpack_from("<II", data, pos + 24)
        if 32 < total < 4 << 20 and 0 < nchunks < 32:
            shaders += 1
            blob = data[pos: pos + total]
            found = False
            for i in range(nchunks):
                off = struct.unpack_from("<I", blob, 32 + 4 * i)[0]
                if blob[off: off + 4] != b"RDEF":
                    continue
                c = off + 8
                _, _, nres, roff = struct.unpack_from("<IIII", blob, c)
                for r in range(nres):
                    name_off, typ, ret, dim, nsamp, bp, bc, fl = struct.unpack_from("<8I", blob, c + roff + 32 * r)
                    if dim in (6, 7):  # TEXTURE2DMS / TEXTURE2DMSARRAY
                        nm = blob[c + name_off: blob.index(b"\0", c + name_off)].decode("ascii", "replace")
                        counts[nsamp] += 1
                        names["%s<%d>" % (nm, nsamp)] += 1
                        found = True
            ms_shaders += found
            pos = data.find(b"DXBC", pos + max(total, 4))
            continue
    except (struct.error, ValueError):
        pass
    pos = data.find(b"DXBC", pos + 4)
print("DXBC shaders: %d, using MS textures: %d" % (shaders, ms_shaders))
print("declared sample counts (0 = unspecified, works with any count):", dict(counts))
print("top MS bindings:", names.most_common(25))
