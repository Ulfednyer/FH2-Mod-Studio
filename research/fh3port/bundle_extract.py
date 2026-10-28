"""Extracts the files of a .NET single-file bundle (apphost) into an output folder."""
import struct, zlib, os, sys

SIG = bytes.fromhex("8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae")
src, out = sys.argv[1], sys.argv[2]
d = open(src, "rb").read()
p = d.find(SIG)
hdr = struct.unpack_from("<q", d, p - 8)[0]
pos = hdr
major, minor, count = struct.unpack_from("<IIi", d, pos); pos += 12


def rstr(pos):
    n, shift = 0, 0
    while True:
        b = d[pos]; pos += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
    return d[pos:pos + n].decode("utf-8"), pos + n


bid, pos = rstr(pos)
if major >= 2:
    pos += 8 * 4 + 8  # deps.json offset/size, runtimeconfig offset/size, flags
print("bundle v%d.%d, %d files, id %s" % (major, minor, count, bid))
os.makedirs(out, exist_ok=True)
for _ in range(count):
    off, size = struct.unpack_from("<qq", d, pos); pos += 16
    csize = 0
    if major >= 6:
        csize = struct.unpack_from("<q", d, pos)[0]; pos += 8
    ftype = d[pos]; pos += 1
    name, pos = rstr(pos)
    data = d[off:off + (csize or size)]
    if csize:
        data = zlib.decompress(data, -15)
    if not name.startswith(("System.", "Microsoft.")) and not name.endswith((".so",)):
        print("%-60s %10d %s" % (name, size, "compressed" if csize else ""))
    dst = os.path.join(out, name)
    os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
    open(dst, "wb").write(data)
