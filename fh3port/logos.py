"""Manufacturer logos for makes FH2 has no logo file for.

List_CarMake.IconPath / IconPathLarge name swatchbins (game:\\Media\\Stripped\\RC0\\Manu_Logo_FOR.swatchbin; a game
path's folder X is X.zip). FH2's own rows for makes it never shipped a car of (Holden, Chrysler) point at RC0 files
that don't exist, and makes the porter added from FH3 (Hoonigan, Hot Wheels) keep FH3 paths (RC21, RC17,
UI\\Textures\\Data_Bound\\Manufacturer_Logos) FH2 doesn't have either -> no logo in the Autoshow. The logos are taken
from FH3 (the row's own paths, then any stripped\\RC*.zip with Manu_Logo_<code> / L_Manu_Logo_<code>), stored in
RCFH3.zip with the thumbnails and the rows pointed there.
"""
import os
import re
import zipfile

import fh3lib


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
