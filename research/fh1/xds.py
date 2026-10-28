"""Forza Horizon 1 / Forza Motorsport 4 .xds textures (Xbox 360) -> linear BCn / DDS / PNG preview.

Layout: 52-byte big-endian header = D3D resource header (7 dwords: common type 3, ref count, fences, identifier,
base/mip flush) + the Xenos GPU texture fetch constant (6 dwords), then the texture data (base level at 0, mips at
mip_address * 4096). Fetch constant fields used (Xenia's xe_gpu_texture_fetch_t):
  d0: type 2 bits, pitch (bits 22-30, in 32-texel units), tiled (bit 31)
  d1: format (bits 0-5), endian (bits 6-7: 1 = 8-in-16 swap), base address (bits 12-31, 4 KB units)
  d2: width - 1 (bits 0-12), height - 1 (bits 13-25)
  d4: mip_max_level (bits 6-9)
  d5: dimension (bits 9-10, 1 = 2D), packed mips (bit 11), mip address (bits 12-31, 4 KB units)
Tiled surfaces: XGAddress2DTiledOffset on 4x4 blocks, each level's width/height rounded to a power of two and
aligned to 32 blocks. Mips are packed into one shared 32x32-block tile once a level's short side is <= 16 texels;
those small levels are rebuilt here from the last unpacked level (box filter + simple BC encoder) instead of
decoding the packed tile.

Usage: py xds.py info <file.xds>...
       py xds.py dds  <file.xds> <out.dds>
       py xds.py png  <file.xds> <out.png>        (base level preview)
"""
import struct
import sys
import zlib

import numpy as np

# Xenos texture formats -> (name, bytes per 4x4 block or per texel, block size, DDS FourCC)
FORMATS = {
    18: ("DXT1", 8, 4, b"DXT1"), 51: ("DXT1", 8, 4, b"DXT1"),
    19: ("DXT3", 16, 4, b"DXT3"), 52: ("DXT3", 16, 4, b"DXT3"),
    20: ("DXT5", 16, 4, b"DXT5"), 53: ("DXT5", 16, 4, b"DXT5"),
    49: ("DXN", 16, 4, b"ATI2"), 59: ("DXT5A", 8, 4, b"ATI1"),
    6: ("A8R8G8B8", 4, 1, None),
}


class Xds:
    def __init__(self, d):
        if len(d) < 52:
            raise ValueError("too small for an xds header")
        h = struct.unpack(">13I", d[:52])
        if h[0] != 3:
            raise ValueError("not a texture resource (type %d)" % h[0])
        d0, d1, d2, d3, d4, d5 = h[7:13]
        self.format = d1 & 0x3F
        if self.format not in FORMATS:
            raise ValueError("unsupported Xenos texture format %d" % self.format)
        self.name, self.bpb, self.block, self.fourcc = FORMATS[self.format]
        self.endian = (d1 >> 6) & 3
        self.tiled = bool(d0 >> 31)
        self.width = (d2 & 0x1FFF) + 1
        self.height = ((d2 >> 13) & 0x1FFF) + 1
        self.mips = ((d4 >> 6) & 0xF) + 1 if d4 else 1
        self.packed = bool((d5 >> 11) & 1)
        self.base = (d1 >> 12) << 12
        self.mip_address = (d5 >> 12) << 12
        self.dimension = (d5 >> 9) & 3
        if self.dimension not in (0, 1):
            raise ValueError("only 2D textures (dimension %d)" % self.dimension)
        self.data = d[52:]

    # ── raw level data ──
    def _blocks(self, px):
        return max(1, (px + self.block - 1) // self.block)

    def _level_dims(self, level):
        """(width, height) in texels of a mip level and its stored (power-of-two, 32-block aligned) block extent."""
        w, h = max(1, self.width >> level), max(1, self.height >> level)
        if level == 0:
            sw, sh = self._blocks(self.width), self._blocks(self.height)
        else:
            sw = self._blocks(max(1, _pow2(self.width) >> level))
            sh = self._blocks(max(1, _pow2(self.height) >> level))
        if self.tiled:
            sw, sh = (sw + 31) & ~31, (sh + 31) & ~31
        return w, h, sw, sh

    def is_packed(self, level):
        if level == 0 or not self.packed:
            return False
        return min(max(1, _pow2(self.width) >> level), max(1, _pow2(self.height) >> level)) <= 16

    def stored_levels(self):
        """Levels that live in their own surface (decodable directly)."""
        return [l for l in range(self.mips) if not self.is_packed(l)]

    def level(self, level):
        """Linear (untiled, little-endian) block data of a stored level, cropped to the level's size."""
        w, h, sw, sh = self._level_dims(level)
        if level == 0:
            off = self.base
        else:
            off = self.mip_address
            for l in range(1, level):
                _, _, pw, ph = self._level_dims(l)
                off += pw * ph * self.bpb
        size = sw * sh * self.bpb
        raw = np.frombuffer(self.data[off:off + size], np.uint8)
        if len(raw) < size:
            raise ValueError("level %d: data ends early (%d of %d bytes)" % (level, len(raw), size))
        if self.endian == 1:          # 8-in-16
            raw = raw.reshape(-1, 2)[:, ::-1].reshape(-1)
        elif self.endian == 2:        # 8-in-32
            raw = raw.reshape(-1, 4)[:, ::-1].reshape(-1)
        blocks = raw.reshape(-1, self.bpb)
        if self.tiled:
            ys, xs = np.mgrid[0:sh, 0:sw]
            idx = _tiled_index(xs.ravel(), ys.ravel(), sw, self.bpb)
            blocks = blocks[idx].reshape(sh, sw, self.bpb)
        else:
            blocks = blocks.reshape(sh, sw, self.bpb)
        bw, bh = self._blocks(w), self._blocks(h)
        return np.ascontiguousarray(blocks[:bh, :bw]).tobytes(), w, h

    # ── full chain (packed tail rebuilt) ──
    def chain(self):
        """[(linear block bytes, width, height)] for every mip level."""
        out = []
        for l in range(self.mips):
            if not self.is_packed(l):
                out.append(self.level(l))
                continue
            prev, pw, ph = out[-1]
            rgba = decode(prev, pw, ph, self.name)
            w, h = max(1, pw // 2), max(1, ph // 2)
            small = rgba[: h * 2 or 1, : w * 2 or 1].astype(np.float32)
            if pw > 1 and ph > 1:
                small = (small[0::2, 0::2] + small[1::2, 0::2] + small[0::2, 1::2] + small[1::2, 1::2]) / 4
            out.append((encode(np.clip(small + 0.5, 0, 255).astype(np.uint8), self.name), w, h))
        return out


def _pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return p


def _tiled_index(x, y, width, bpb):
    """XGAddress2DTiledOffset: element (block) index in the tiled surface for element (x, y); width in elements,
    already aligned to 32."""
    log_bpp = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}[bpb]
    x = x.astype(np.int64)
    y = y.astype(np.int64)
    aligned = (width + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (aligned >> 5)) << (log_bpp + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log_bpp
    offset = macro + ((micro & ~15) << 1) + (micro & 15) + ((y & 8) << (3 + log_bpp)) + ((y & 1) << 4)
    return ((((offset & ~511) << 3) + ((offset & 448) << 2) + (offset & 63) + ((y & 16) << 7)
             + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6)) >> log_bpp)


# ── BC decode / encode (preview and rebuilt small mips) ──

def _565(c):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.int32)


def _color_block(b, dxt1):
    c0 = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
    c1 = b[:, 2].astype(np.int32) | (b[:, 3].astype(np.int32) << 8)
    p0, p1 = _565(c0), _565(c1)
    four = (c0 > c1) | ~dxt1
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)                      # n, 4, 3
    bits = b[:, 4:8].astype(np.uint32)
    word = bits[:, 0] | (bits[:, 1] << 8) | (bits[:, 2] << 16) | (bits[:, 3] << 24)
    idx = (word[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    rgb = np.take_along_axis(pal, idx[:, :, None].astype(np.int64), 1)
    alpha = np.where((dxt1 & (c0 <= c1))[:, None] & (idx == 3), 0, 255)
    return rgb, alpha


def _alpha_block(b):
    a0, a1 = b[:, 0].astype(np.int32), b[:, 1].astype(np.int32)
    k = np.arange(8)
    eight = np.where(k == 0, a0[:, None], np.where(k == 1, a1[:, None],
                     ((8 - k) * a0[:, None] + (k - 1) * a1[:, None]) // 7))
    six = np.where(k == 0, a0[:, None], np.where(k == 1, a1[:, None], np.where(
        k < 6, ((6 - k) * a0[:, None] + (k - 1) * a1[:, None]) // 5, np.where(k == 6, 0, 255))))
    pal = np.where((a0 > a1)[:, None], eight, six)
    bits = np.zeros(len(b), np.uint64)
    for i in range(6):
        bits |= b[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    idx = (bits[:, None] >> (3 * np.arange(16, dtype=np.uint64))) & np.uint64(7)
    return np.take_along_axis(pal, idx.astype(np.int64), 1)


def decode(data, w, h, name):
    """Linear BC data -> RGBA uint8 array (h, w, 4)."""
    if name == "A8R8G8B8":
        a = np.frombuffer(data, np.uint8).reshape(h, w, 4)
        return a[:, :, [1, 2, 3, 0]].copy()
    bpb = 8 if name in ("DXT1", "DXT5A") else 16
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    b = np.frombuffer(data, np.uint8).reshape(-1, bpb)
    out = np.zeros((len(b), 16, 4), np.int32)
    if name == "DXT1":
        rgb, a = _color_block(b, np.ones(len(b), bool))
        out[:, :, :3], out[:, :, 3] = rgb, a
    elif name == "DXT3":
        rgb, _ = _color_block(b[:, 8:], np.zeros(len(b), bool))
        nib = np.unpackbits(b[:, :8], axis=1, bitorder="little").reshape(-1, 16, 4)
        out[:, :, :3], out[:, :, 3] = rgb, (nib * (1 << np.arange(4))).sum(2) * 17
    elif name == "DXT5":
        rgb, _ = _color_block(b[:, 8:], np.zeros(len(b), bool))
        out[:, :, :3], out[:, :, 3] = rgb, _alpha_block(b[:, :8])
    elif name == "DXN":
        r, g = _alpha_block(b[:, :8]), _alpha_block(b[:, 8:])
        out[:, :, 0], out[:, :, 1], out[:, :, 2], out[:, :, 3] = r, g, 255, 255
    elif name == "DXT5A":
        a = _alpha_block(b)
        out[:, :, 0] = out[:, :, 1] = out[:, :, 2] = a
        out[:, :, 3] = 255
    img = out.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return np.clip(img[:h, :w], 0, 255).astype(np.uint8)


def _enc_color(px):
    """px: (n, 16, 3) -> (n, 8) BC1 colour blocks (endpoints = per-channel min/max, 4-colour mode)."""
    lo, hi = px.min(1), px.max(1)

    def pack(c):
        return ((c[:, 0].astype(np.int32) * 31 + 127) // 255 << 11) | ((c[:, 1].astype(np.int32) * 63 + 127) // 255 << 5) \
            | ((c[:, 2].astype(np.int32) * 31 + 127) // 255)
    c0, c1 = pack(hi), pack(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _565(c0), _565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)
    d = ((px[:, :, None, :].astype(np.int32) - pal[:, None, :, :]) ** 2).sum(3)
    idx = np.where((c0 == c1)[:, None], 0, d.argmin(2)).astype(np.uint32)
    word = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((len(px), 8), np.uint8)
    out[:, 0], out[:, 1], out[:, 2], out[:, 3] = c0 & 255, c0 >> 8, c1 & 255, c1 >> 8
    for i in range(4):
        out[:, 4 + i] = (word >> (8 * i)) & 255
    return out


def _enc_alpha(a):
    """a: (n, 16) -> (n, 8) BC4/DXT5-alpha blocks (8-value mode)."""
    a0, a1 = a.max(1).astype(np.int32), a.min(1).astype(np.int32)
    k = np.arange(8)
    pal = np.where(k == 0, a0[:, None], np.where(k == 1, a1[:, None], ((8 - k) * a0[:, None] + (k - 1) * a1[:, None]) // 7))
    idx = np.abs(a[:, :, None].astype(np.int32) - pal[:, None, :]).argmin(2).astype(np.uint64)
    idx = np.where((a0 == a1)[:, None], 0, idx)
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((len(a), 8), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for i in range(6):
        out[:, 2 + i] = (bits >> np.uint64(8 * i)) & np.uint64(255)
    return out


def encode(rgba, name):
    h, w = rgba.shape[:2]
    if name == "A8R8G8B8":
        return rgba[:, :, [3, 0, 1, 2]].tobytes()
    bh, bw = (h + 3) // 4, (w + 3) // 4
    pad = np.zeros((bh * 4, bw * 4, 4), np.uint8)
    pad[:h, :w] = rgba
    pad[h:, :w] = rgba[h - 1:h, :w] if h else 0
    pad[:, w:] = pad[:, w - 1:w]
    px = pad.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4)
    if name == "DXT1":
        blocks = _enc_color(px[:, :, :3])
    elif name in ("DXT3", "DXT5"):
        alpha = _enc_alpha(px[:, :, 3]) if name == "DXT5" else np.packbits(
            ((px[:, :, 3].astype(np.int32) + 8) // 17)[:, :, None] >> np.arange(4) & 1, axis=1, bitorder="little").reshape(-1, 8)
        blocks = np.concatenate([alpha, _enc_color(px[:, :, :3])], 1)
    elif name == "DXN":
        blocks = np.concatenate([_enc_alpha(px[:, :, 0]), _enc_alpha(px[:, :, 1])], 1)
    elif name == "DXT5A":
        blocks = _enc_alpha(px[:, :, 0])
    return blocks.astype(np.uint8).tobytes()


# ── output ──

def to_dds(x):
    chain = x.chain()
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000
    if x.fourcc:
        pf = struct.pack("<II4sIIIII", 32, 0x4, x.fourcc, 0, 0, 0, 0, 0)
        pitch = len(chain[0][0])
    else:
        pf = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000)
        pitch, flags = x.width * 4, flags & ~0x80000 | 0x8
    hdr = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, x.height, x.width, pitch, 0, len(chain)) + pf \
        + struct.pack("<IIIII", 0x1000 | 0x400000 | 0x8, 0, 0, 0, 0)
    return hdr + b"".join(c[0] for c in chain)


def to_png(rgba):
    h, w = rgba.shape[:2]
    raw = b"".join(b"\0" + rgba[y].tobytes() for y in range(h))

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def main(argv):
    if len(argv) >= 2 and argv[0] == "info":
        for f in argv[1:]:
            x = Xds(open(f, "rb").read())
            print("%s: %s %dx%d, %d mips (%d stored, packed tail %s), tiled %s, endian %d" % (
                f, x.name, x.width, x.height, x.mips, len(x.stored_levels()), x.packed, x.tiled, x.endian))
    elif len(argv) == 3 and argv[0] == "dds":
        open(argv[2], "wb").write(to_dds(Xds(open(argv[1], "rb").read())))
    elif len(argv) == 3 and argv[0] == "png":
        x = Xds(open(argv[1], "rb").read())
        data, w, h = x.level(0)
        open(argv[2], "wb").write(to_png(decode(data, w, h, x.name)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
