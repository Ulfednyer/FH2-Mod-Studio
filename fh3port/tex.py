"""FH3 -> FH2 texture (.swatchbin) fix-ups.

FH2 has two texture readers (sub_1410DBB90, called from Texture11::vf0D):
  * BCXT blob version 2.0  -> Xbox One tiled data with FH2's compact 35-byte TXCH header;
  * any other version      -> "PC" path (sub_1410DC470): a relocatable header (pointer chains at +0 / +4) with the
    D3D11 description at header+8: +16 u32 width, +20 height, +24 depth, +28 u16 arraySize, +30 u8 mips,
    +31 u8 cube flag (ANY non-zero = TEXTURECUBE), +32 i32 format, +40 i32 sRGB, +48 ptr -> (i32 format, mip tables).
FH3 PC textures are BCXT version 0.0 with exactly that header, so FH2 loads them linearly - no re-tiling needed - once
the converter has rewritten the container to bundle 1.0.  Two things still break them:
  1. FH3 sets byte +31 to 2 on UI textures (thumbnails, gauge needles, gear digits...), FH2 reads that as "cubemap"
     with one slice -> CreateTexture2D fails -> default white texture.  Real cubemaps use 1 with arraySize 6.
  2. Block-compressed textures whose top mip is not a multiple of 4 (e.g. thumbnails 816x459) are rejected by D3D11.
     The data is already padded to whole blocks, so the size is rounded up when every mip keeps its block count.

Usage: py tex.py check <zip>...     report what would change
       py tex.py fix <in.zip> <out.zip>
"""
import struct
import sys
import zipfile

BC_DXGI = set(range(70, 85)) | set(range(94, 100))
# FH2's format table (dword_142E7F304 / ..308): format id -> (DXGI, DXGI sRGB)
FORMATS = {0: (71, 72), 1: (74, 75), 2: (77, 78), 3: (80, 80), 4: (81, 81), 5: (83, 83), 6: (84, 84), 7: (95, 0),
           8: (96, 0), 9: (98, 99), 10: (2, 0), 11: (11, 0), 12: (10, 0), 13: (28, 29), 14: (85, 0), 15: (86, 0),
           19: (61, 0), 20: (65, 0)}


def _layout(d):
    """Returns (meta offset, blob version) for an FH2-container (bundle 1.0) texture, else None."""
    if len(d) < 40 or d[:4] != b"burG" or d[4:6] != b"\x01\x00":
        return None
    count = struct.unpack_from("<H", d, 6)[0]
    for i in range(count):
        tag, vmaj, vmin, mcount, moff = struct.unpack_from("<4sBBHI", d, 16 + 24 * i)
        if tag != b"BCXT":
            continue
        for k in range(mcount):
            mtag, _, rel = struct.unpack_from("<4sHH", d, moff + 8 * k)
            if mtag == b"HCXT":
                return moff + 8 * k + rel, (vmaj, vmin)
    return None


def _ptr(d, meta, field):
    """Target offset (relative to meta) of the base-chain pointer stored at meta+field, or None."""
    v = struct.unpack_from("<I", d, meta)[0]
    while v != 0xFFFFFFFF:
        tgt, nxt = struct.unpack_from("<II", d, meta + v)
        if v == field:
            return tgt
        v = nxt
    return None


def _dxgi(d, meta):
    a3 = meta + 8
    fa, cs = struct.unpack_from("<i", d, a3 + 32)[0], struct.unpack_from("<i", d, a3 + 40)[0]
    if fa <= 1:
        p = _ptr(d, meta, 56)
        if p is None:
            return None
        fa = struct.unpack_from("<i", d, meta + p)[0]
    pair = FORMATS.get(fa)
    return None if pair is None else pair[1 if cs == 1 else 0]


def _blocks(n, mips):
    return [(max(1, n >> m) + 3) // 4 for m in range(mips)]


def fix_bytes(d):
    """Returns (new bytes or None, list of changes)."""
    lay = _layout(d)
    if not lay or lay[1] == (2, 0):
        return None, []
    meta = lay[0]
    a3 = meta + 8
    out = bytearray(d)
    changes = []
    w, h = struct.unpack_from("<II", d, a3 + 16)
    arr = struct.unpack_from("<H", d, a3 + 28)[0] & 0x3FFF
    mips, flag = d[a3 + 30], d[a3 + 31]
    want = 1 if (flag & 1 and arr % 6 == 0) else 0
    if flag != want:
        out[a3 + 31] = want
        changes.append("flag %d->%d" % (flag, want))
    dx = _dxgi(d, meta)
    if dx in BC_DXGI and (w % 4 or h % 4):
        w4, h4 = (w + 3) & ~3, (h + 3) & ~3
        if _blocks(w, mips) == _blocks(w4, mips) and _blocks(h, mips) == _blocks(h4, mips):
            struct.pack_into("<II", out, a3 + 16, w4, h4)
            changes.append("size %dx%d->%dx%d" % (w, h, w4, h4))
        else:
            changes.append("WARN odd BC size %dx%d mips %d kept" % (w, h, mips))
    if not changes or all(c.startswith("WARN") for c in changes):
        return None, changes
    return bytes(out), changes


def fix_zip(src, dst):
    changed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".swatchbin"):
                new, _ = fix_bytes(data)
                if new is not None:
                    data = new
                    changed += 1
            zout.writestr(info.filename, data)
    return changed


def main(argv):
    if len(argv) >= 2 and argv[0] == "check":
        for zp in argv[1:]:
            with zipfile.ZipFile(zp) as z:
                for n in z.namelist():
                    if n.lower().endswith(".swatchbin"):
                        _, ch = fix_bytes(z.read(n))
                        if ch:
                            print(n, ", ".join(ch))
        return 0
    if len(argv) == 3 and argv[0] == "fix":
        print("fixed %d textures" % fix_zip(argv[1], argv[2]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
