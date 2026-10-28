"""Write textures as FH2 .swatchbin (the "PC" texture layout FH2 loads linearly: BCXT blob version 0.0, see
fh3port\\tex.py) - used for FH1 / FM4 .xds textures (xds.py).

File = burG 1.0 bundle with one BCXT 0.0 blob; its HCXT metadata is the texture header, the blob data the mip chain
(linear, level 0 first). Header (offsets from its start; measured on FH2-loaded FH3 car textures):
  +00 u32 0x38   first pointer field (relocation chain: each pointer is (target, next pointer field), -1 ends)
  +04 u32 0x50
  +08 guid16     texture id (every FH2-loaded car texture has one)
  +18 u32 width, +1C height, +20 depth (1)
  +24 u16 array size (1), u8 mip count, u8 cube flag (0; FH2 treats any non-zero as a cubemap)
  +28 i32 0      (format taken from the pointed-to block below)
  +2C i32 sRGB, +30 i32 sRGB   both 1 for colour textures (format id -> DXGI _SRGB variant)
  +38 ptr 0x40 -> +40 i32 format id (FH2 table, tex.FORMATS: 0 BC1, 1 BC2, 2 BC3, 3 BC4, 5 BC5, 9 BC7, 13 RGBA8)
  +44 ptr 0x4C -> mip list: per level (size, offset into the blob data, next) 12 bytes, next = following entry + 4
Header length 0x4C + 12 * mips. rebuild() reproduces FH2's own files byte for byte (py swatch.py test <zip>).

Usage: py swatch.py test <car zip>...                   rebuild every swatchbin of the zips from its fields
       py swatch.py xds <in.xds> <out.swatchbin> [name]  convert one FH1 texture
"""
import os
import struct
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "fh3port"))
import bundle  # noqa: E402

# xds.Xds.name -> FH2 format id
FORMAT_IDS = {"DXT1": 0, "DXT3": 1, "DXT5": 2, "DXT5A": 3, "DXN": 5, "A8R8G8B8": 13}
GUID_NS = uuid.UUID("6f1c7a52-2b64-4f3e-9d0a-f4e1c0de0001")


def header(width, height, mip_sizes, format_id, srgb, guid):
    n = len(mip_sizes)
    h = bytearray(0x4C + 12 * n)
    struct.pack_into("<II", h, 0, 0x38, 0x50)
    h[8:24] = guid
    struct.pack_into("<IIIHBB", h, 0x18, width, height, 1, 1, n, 0)
    struct.pack_into("<iiii", h, 0x28, 0, 1 if srgb else 0, 1 if srgb else 0, 0)
    struct.pack_into("<IIiII", h, 0x38, 0x40, 0x44, format_id, 0x4C, 0xFFFFFFFF)
    off = 0
    for i, size in enumerate(mip_sizes):
        nxt = 0x4C + 12 * (i + 1) + 4 if i + 1 < n else 0xFFFFFFFF
        struct.pack_into("<III", h, 0x4C + 12 * i, size, off, nxt)
        off += size
    return bytes(h)


def build(width, height, mips, format_id, srgb, guid):
    """mips: [bytes] level 0 first -> .swatchbin bytes."""
    hdr = header(width, height, [len(m) for m in mips], format_id, srgb, guid)
    return bundle.serialize([bundle.Blob(b"BCXT", (0, 0), [(b"HCXT", 0, hdr)], b"".join(mips))])


def fields(d):
    """An FH2-layout swatchbin -> (width, height, [mip bytes], format id, srgb, guid) (inverse of build)."""
    blob = next(b for b in bundle.parse(d) if b.tag == b"BCXT")
    if blob.ver != (0, 0):
        raise ValueError("BCXT %d.%d is FH2's own tiled layout, not the PC layout" % blob.ver)
    h = blob.meta(b"HCXT")
    w, hh = struct.unpack_from("<II", h, 0x18)
    n = h[0x26]
    fid, srgb = struct.unpack_from("<i", h, 0x40)[0], struct.unpack_from("<i", h, 0x30)[0]
    mips = []
    for i in range(n):
        size, off, _ = struct.unpack_from("<III", h, 0x4C + 12 * i)
        mips.append(blob.data[off:off + size])
    return w, hh, mips, fid, srgb, bytes(h[8:24])


def from_xds(x, name):
    """xds.Xds -> .swatchbin bytes. sRGB from the texture's gamma sign bits; GUID derived from the name (stable)."""
    if x.name not in FORMAT_IDS:
        raise ValueError("no FH2 format for " + x.name)
    chain = x.chain()
    mips = [c[0] for c in chain]
    if x.name == "A8R8G8B8":   # xds texels are B, G, R, A in memory; FH2's format 13 is R8G8B8A8
        mips = [_argb_to_rgba(b) for b in mips]
    guid = uuid.uuid5(GUID_NS, name.lower()).bytes_le
    return build(x.width, x.height, mips, FORMAT_IDS[x.name], x.srgb, guid)


def _argb_to_rgba(b):
    import numpy as np
    a = np.frombuffer(b, np.uint8).reshape(-1, 4)
    return a[:, [2, 1, 0, 3]].tobytes()


def main(argv):
    if len(argv) >= 2 and argv[0] == "test":
        import zipfile
        same = diff = 0
        for zp in argv[1:]:
            z = zipfile.ZipFile(zp)
            for n in z.namelist():
                if not n.lower().endswith(".swatchbin"):
                    continue
                d = z.read(n)
                try:
                    w, h, mips, fid, srgb, guid = fields(d)
                except (ValueError, StopIteration, struct.error):
                    continue
                if build(w, h, mips, fid, srgb, guid) == d:
                    same += 1
                else:
                    diff += 1
                    if diff <= 5:
                        print("differs:", n)
        print("identical", same, "different", diff)
    elif len(argv) >= 3 and argv[0] == "xds":
        import xds
        x = xds.Xds(open(argv[1], "rb").read())
        open(argv[2], "wb").write(from_xds(x, argv[3] if len(argv) > 3 else os.path.basename(argv[1])))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
