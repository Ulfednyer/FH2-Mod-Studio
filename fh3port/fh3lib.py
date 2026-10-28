"""FH3 media lookup across several media folders and FH3's layered library zips.

Media folders (ROOTS, highest priority first): the extra folders from fh3port.ini (`fh3_extra`, e.g. an update/DLC
media tree kept apart from the install) followed by <fh3 install>\\media. A file is taken from the first folder that
has it: car zips, the database (stripped\\gamedbRC.slt), string tables, thumbnails (stripped\\RC*.zip), physics files.

Library zips are layered inside each folder too: media/cars/_library/Materials.zip plus patch zips
Materials_pri_44.zip and Materials_pri_45.zip (same for Textures). The patch zips add files (paints of later cars:
greenhellmagno for the AMG GT R, darkgreenbenspeed6 for the EXP 10 Speed 6 ...) and override older ones; the higher
_pri_ number wins. LayeredZip(".../Materials.zip") reads like a zipfile.ZipFile (namelist, read) over all layers of all
media folders. Names are matched case-insensitively (the DLC tree has materials_pri_44.zip).
"""
import glob
import os
import re
import zipfile

ROOTS = []


def set_roots(roots):
    ROOTS[:] = [os.path.normpath(r) for r in roots if r and os.path.isdir(r)]


def _rel(path):
    """(root, path relative to it) for a path inside one of the media folders, else (None, path)."""
    p = os.path.normcase(os.path.normpath(path))
    for r in ROOTS:
        rr = os.path.normcase(r)
        if p == rr or p.startswith(rr + os.sep):
            return r, os.path.normpath(path)[len(r) + 1:]
    return None, path


def find(rel):
    """First media folder's copy of rel (e.g. 'stripped/gamedbRC.slt'), or None."""
    for r in ROOTS:
        p = os.path.join(r, rel)
        if os.path.exists(p):
            return p
    return None


def find_all(rel):
    return [p for p in (os.path.join(r, rel) for r in ROOTS) if os.path.exists(p)]


def listdir(rel, suffix=""):
    """{lower name: path} of files in rel across media folders, the first folder winning."""
    out = {}
    for r in ROOTS:
        d = os.path.join(r, rel)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith(suffix.lower()) and os.path.isfile(os.path.join(d, f)):
                    out.setdefault(f.lower(), os.path.join(d, f))
    return out


def _layers_in(base_zip):
    stem, ext = os.path.splitext(base_zip)
    pri = []
    for p in glob.glob(glob.escape(stem) + "_pri_*" + ext):
        m = re.search(r"(?i)_pri_(\d+)$", os.path.splitext(p)[0])
        if m:
            pri.append((int(m.group(1)), p))
    return [p for _, p in sorted(pri, reverse=True)] + ([base_zip] if os.path.exists(base_zip) else [])


def layers(base_zip):
    """[highest priority zip, ..., lowest] for a library zip: every media folder's patch zips and base zip."""
    root, rel = _rel(base_zip)
    if root is None:
        return _layers_in(base_zip)
    out = []
    for r in ROOTS:
        out += _layers_in(os.path.join(r, rel))
    return out


class LayeredZip:
    def __init__(self, base_zip):
        self.zips = [zipfile.ZipFile(p) for p in layers(base_zip)]
        self.index = {}
        for z in self.zips:
            for n in z.namelist():
                self.index.setdefault(n.lower(), (z, n))
        self.names = [n for _, n in self.index.values()]

    def namelist(self):
        return list(self.names)

    def read(self, name):
        z, n = self.index[name.lower()]
        return z.read(n)

    def close(self):
        for z in self.zips:
            z.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def merged_zip(base_zip, out_zip):
    """One zip with every layer's files (highest priority wins), for tools that read a single library zip (the
    converter's --fh3-lib). Rebuilt only when a layer is newer than out_zip."""
    srcs = layers(base_zip)
    if os.path.exists(out_zip) and all(os.path.getmtime(s) <= os.path.getmtime(out_zip) for s in srcs):
        return out_zip
    os.makedirs(os.path.dirname(out_zip), exist_ok=True)
    tmp = "%s.%d.tmp" % (out_zip, os.getpid())
    with LayeredZip(base_zip) as lz, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in sorted(lz.namelist()):
            zout.writestr(n, lz.read(n))
    try:
        os.replace(tmp, out_zip)
    except PermissionError:             # another process is using a copy it just built: keep that one
        os.remove(tmp)
        if not os.path.exists(out_zip):
            raise
    return out_zip


def priority(zip_name):
    """Sort key: patch zips first, higher _pri_ first, base zip last."""
    m = re.search(r"(?i)_pri_(\d+)\.zip$", zip_name)
    return -int(m.group(1)) if m else 0
