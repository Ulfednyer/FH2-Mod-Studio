"""Manufacturer logos for makes FH2 has no logo file for.

List_CarMake.IconPath / IconPathLarge name swatchbins (game:\\Media\\Stripped\\RC0\\Manu_Logo_FOR.swatchbin; a game
path's folder X is X.zip). FH2's own rows for makes it never shipped a car of (Holden, Chrysler) point at RC0 files
that don't exist, and makes the porter added from FH3 (Hoonigan, Hot Wheels) keep FH3 paths (RC21, RC17,
UI\\Textures\\Data_Bound\\Manufacturer_Logos) FH2 doesn't have either -> no logo in the Autoshow. The logos are taken
from FH3 (the row's own paths, then any stripped\\RC*.zip with Manu_Logo_<code> / L_Manu_Logo_<code>), stored in
RCFH3.zip with the thumbnails and the rows pointed there.

FH2's UI stretches a logo over a fixed box: every FH2 logo is 440x376 (L_) or 220x184. FH3's large logos have their
own shape (BAC 400x72, Alumi Craft 372x120), so FH2 showed them stretched tall. `fit()` pads them with transparent
blocks to FH2's aspect ratio (block-compressed data is moved block by block, nothing is re-encoded).
"""
import os
import re
import struct
import zipfile

import fh3lib
import tex

FH2_SIZE = {True: (440, 376), False: (220, 184)}      # (large?) -> FH2's logo canvas
# DXGI format -> (block edge in pixels, bytes per block, one fully transparent block)
_BLANK = {98: (4, 16, b"\x40" + bytes(15)), 99: (4, 16, b"\x40" + bytes(15)),   # BC7 mode 6, colour and alpha 0
          77: (4, 16, bytes(16)), 78: (4, 16, bytes(16)),                       # BC3, alpha 0
          28: (1, 4, bytes(4)), 29: (1, 4, bytes(4))}                           # R8G8B8A8


def _canvas(w, h, tw, th, edge):
    """Smallest canvas >= (w, h) with the aspect ratio tw:th, in whole blocks."""
    if w * th >= h * tw:
        cw, ch = w, -(-w * th // tw)
    else:
        cw, ch = -(-h * tw // th), h
    up = lambda v: -(-v // edge) * edge
    return up(cw), up(ch)


def fit(data, large):
    """FH2-container (bundle 1.0) logo swatchbin -> same texture padded to FH2's logo aspect ratio, or None when it
    already fits or can't be handled (mipmapped, unknown format)."""
    lay = tex._layout(data)
    if not lay or lay[1] == (2, 0):
        return None
    meta = lay[0]
    a3 = meta + 8
    w, h = struct.unpack_from("<II", data, a3 + 16)
    if data[a3 + 30] != 1 or tex._dxgi(data, meta) not in _BLANK:
        return None
    edge, bsize, blank = _BLANK[tex._dxgi(data, meta)]
    tw, th = FH2_SIZE[large]
    if abs(w * th - h * tw) < edge * max(tw, th):       # already FH2's shape (up to one block of rounding)
        return None
    cw, ch = _canvas(w, h, tw, th, edge)
    # blob entry: tag, version, meta count, meta offset, data offset, size, size again
    count = struct.unpack_from("<H", data, 6)[0]
    for i in range(count):
        tag, _, _, _, _, doff, size, size2 = struct.unpack_from("<4sBBHIIII", data, 16 + 24 * i)
        if tag == b"BCXT":
            entry = 16 + 24 * i
            break
    else:
        return None
    bw, bh, nbw, nbh = -(-w // edge), -(-h // edge), cw // edge, ch // edge
    if size != bw * bh * bsize:
        return None
    ox, oy = (nbw - bw) // 2, (nbh - bh) // 2
    pix = bytearray(blank * (nbw * nbh))
    for y in range(bh):
        src = doff + y * bw * bsize
        dst = ((oy + y) * nbw + ox) * bsize
        pix[dst:dst + bw * bsize] = data[src:src + bw * bsize]
    new_size = len(pix)
    head = bytearray(data[:doff])
    # the mip table holds the data size once more; it is the only other copy of it in the header
    hits = [o for o in range(meta, doff - 3, 4) if struct.unpack_from("<I", head, o)[0] == size and o != entry + 16]
    if len(hits) != 1:
        return None
    struct.pack_into("<I", head, hits[0], new_size)
    struct.pack_into("<II", head, a3 + 16, cw, ch)
    struct.pack_into("<II", head, entry + 16, new_size, new_size)
    tail = data[doff + size:]
    struct.pack_into("<I", head, 12, len(head) + new_size + len(tail))
    return bytes(head) + bytes(pix) + tail


def fit_files(files):
    """{name: FH2-container bytes}: logo entries (Manu_Logo_* / L_Manu_Logo_*) padded to FH2's shape."""
    out = {}
    for n, b in files.items():
        base = n.rsplit("/", 1)[-1].lower()
        if base.startswith(("manu_logo_", "l_manu_logo_")):
            b = fit(b, base.startswith("l_")) or b
        out[n] = b
    return out


def _resolve(media_root, game_path, open_zip=None):
    """(zip path, name inside) or (loose path, None) for game:\\media\\... under media_root, else None."""
    m = re.match(r"(?i)game:[\\/]+media[\\/]+(.+)", game_path or "")
    if not m:
        return None
    parts = re.split(r"[\\/]+", m.group(1))
    loose = os.path.join(media_root, *parts)
    if os.path.isfile(loose):
        return loose, None
    for i in range(len(parts) - 1, 0, -1):
        zp = os.path.join(media_root, *parts[:i]) + ".zip"
        if os.path.isfile(zp):
            want = "/".join(parts[i:]).lower()
            with zipfile.ZipFile(zp) as z:
                hit = next((n for n in z.namelist() if n.lower().replace("\\", "/") == want), None)
            return (zp, hit) if hit else None
    return None


def fh2_has(fh2_media, game_path):
    return _resolve(fh2_media, game_path) is not None


def _read(hit):
    path, name = hit
    if name is None:
        return open(path, "rb").read()
    with zipfile.ZipFile(path) as z:
        return z.read(name)


def fh3_logo(fh3_paths, code, large):
    """FH3 bytes of a make's logo: its FH3 row paths in every media folder, then any RC zip."""
    for p in fh3_paths:
        for root in fh3lib.ROOTS:
            hit = _resolve(root, p)
            if hit:
                return _read(hit)
    want = ("l_manu_logo_%s.swatchbin" if large else "manu_logo_%s.swatchbin") % code.lower()
    for f, zp in sorted(fh3lib.listdir("stripped", ".zip").items()):
        with zipfile.ZipFile(zp) as z:
            hit = next((n for n in z.namelist() if n.lower() == want), None)
            if hit:
                return z.read(hit)
    return None


def missing_logos(fh2_db, fh3_db, fh2_media, make_ids):
    """{zip name: FH3 bytes} to add to RCFH3.zip and {make id: (IconPath, IconPathLarge)} for the makes in make_ids
    whose logos FH2 can't load. Makes FH3 has no logo for either are left alone."""
    files, rows = {}, {}
    for mid, code, ip, il in fh2_db.execute("SELECT ID, ManufacturerCode, IconPath, IconPathLarge FROM List_CarMake"):
        if mid not in make_ids or (fh2_has(fh2_media, ip) and fh2_has(fh2_media, il)):
            continue
        r3 = fh3_db.execute("SELECT IconPath, IconPathLarge FROM List_CarMake WHERE UPPER(ManufacturerCode) = UPPER(?)",
                            (code,)).fetchone() or (None, None)
        small = fh3_logo([x for x in (r3[0], ip) if x], code, False)
        large = fh3_logo([x for x in (r3[1], il) if x], code, True)
        if small is None and large is None:
            continue
        small, large = small or large, large or small
        n_small, n_large = "Manu_Logo_%s.swatchbin" % code, "L_Manu_Logo_%s.swatchbin" % code
        files[n_small], files[n_large] = small, large
        rows[mid] = ("game:\\Media\\Stripped\\RCFH3\\" + n_small, "game:\\Media\\Stripped\\RCFH3\\" + n_large)
    return files, rows
