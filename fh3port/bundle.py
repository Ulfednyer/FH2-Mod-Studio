"""Full read/write model of a burG 1.0 bundle (FH2 layout), so blobs can be added/removed.

Layout: 16-byte header (magic, u8 maj, u8 min, u16 count, u32 header size, u32 total size), count x 24-byte entries
(tag, u8 maj, u8 min, u16 metaCount, u32 metaOffset, u32 dataOffset, u32 size, u32 uncompressedSize), then per blob
its metadata table (8-byte entries: tag, u16 size<<4|ver, u16 offset relative to that entry) followed by the metadata
payloads; then the blob data. serialize() reproduces FH2's own files byte for byte (checked with `py bundle.py test`).
"""
import struct
import sys
import zipfile


class Blob:
    __slots__ = ("tag", "ver", "metas", "data", "usize")

    def __init__(self, tag, ver, metas, data, usize=None):
        self.tag, self.ver, self.metas, self.data = tag, ver, metas, data
        self.usize = len(data) if usize is None else usize

    def meta(self, tag):
        for t, v, d in self.metas:
            if t == tag:
                return d
        return None


class Layout:
    """Remembers how the source file placed things, to reproduce it."""
    meta_gap = 0
    data_align = 4


def parse(d):
    if d[:4] != b"burG" or d[4:6] != b"\x01\x00":
        raise ValueError("not a burG 1.0 bundle")
    count, hsize, total = struct.unpack_from("<HII", d, 6)
    blobs = []
    for i in range(count):
        tag, vmaj, vmin, mc, mo, do, size, usize = struct.unpack_from("<4sBBHIIII", d, 16 + 24 * i)
        metas = []
        for k in range(mc):
            mt, sv, rel = struct.unpack_from("<4sHH", d, mo + 8 * k)
            p = mo + 8 * k + rel
            metas.append((mt, sv & 15, d[p:p + (sv >> 4)]))
        blobs.append(Blob(tag, (vmaj, vmin), metas, d[do:do + size], usize))
    return blobs


def serialize(blobs):
    n = len(blobs)
    head = bytearray(16 + 24 * n)
    meta_area = bytearray()
    base = len(head)
    offsets = []
    for b in blobs:
        mo = base + len(meta_area)
        offsets.append(mo)
        table = bytearray(8 * len(b.metas))
        payload = bytearray()
        for k, (mt, mv, md) in enumerate(b.metas):
            rel = 8 * len(b.metas) - 8 * k + len(payload)
            struct.pack_into("<4sHH", table, 8 * k, mt, (len(md) << 4) | mv, rel)
            payload += md
        meta_area += table + payload
    hsize = base + len(meta_area)
    out = head + meta_area
    pos = (len(out) + 3) & ~3
    out += bytes(pos - len(out))
    for i, b in enumerate(blobs):
        # both size fields = the real data length. FH2 never stores anything else (71,748 blobs: size == usize), and
        # FH2 reads blob data by the second field: blobs edited in place kept their old value, so the game read
        # grown VLays truncated - the missing elements repeated the last one read (duplicate TEXCOORD/TANGENT input
        # elements, Azimuth "D3D12 graphics pipeline ... 0x80070057") and grown VerBs lost their tail.
        b.usize = len(b.data)
        struct.pack_into("<4sBBHIIII", out, 16 + 24 * i, b.tag, b.ver[0], b.ver[1], len(b.metas), offsets[i] if b.metas else offsets[i],
                         pos, len(b.data), b.usize)
        out += b.data
        pos += len(b.data)
        pad = ((pos + 3) & ~3) - pos
        out += bytes(pad)
        pos += pad
    struct.pack_into("<4sBBHII", out, 0, b"burG", 1, 0, n, (hsize + 3) & ~3, len(out))  # FH2 stores it 4-aligned
    return bytes(out)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "test":
        same = diff = 0
        for zp in sys.argv[2:]:
            z = zipfile.ZipFile(zp)
            for nm in z.namelist():
                if nm.lower().endswith(".modelbin"):
                    d = z.read(nm)
                    try:
                        r = serialize(parse(d))
                    except ValueError:
                        continue
                    if r == d:
                        same += 1
                    else:
                        diff += 1
                        if diff <= 3:
                            k = next(i for i in range(min(len(r), len(d))) if r[i] != d[i]) if len(r) == len(d) else -1
                            print("differs:", nm, len(d), len(r), "first diff at", k)
        print("identical", same, "different", diff)
