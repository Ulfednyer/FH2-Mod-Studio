"""Resolves every file a ported car refers to: carbin model + AO paths, and each model's MatI material paths, against
the car zip, the car's other zips and Mount\\media\\cars\\_library (loose files and zips). Prints what is missing.
A missing asset can leave the car "loading" forever: the showroom 3D view stays black while the UI works.
    py pathcheck.py <game folder> <MediaName>"""
import glob
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fh3port"))
import bundle
import carbin


def norm(p):
    p = p.replace("/", "\\").lower()
    for pre in ("game:\\media\\", "game:\\"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p


def index(game, car):
    """{path relative to Media, lowercase: source}"""
    have = {}
    media = os.path.join(game, "Mount", "media")
    zips = glob.glob(os.path.join(media, "cars", "*.zip"))   # cars share parts (a donor's materials)
    lib = os.path.join(media, "cars", "_library")
    zips += glob.glob(os.path.join(lib, "**", "*.zip"), recursive=True)
    for zp in zips:
        rel = os.path.relpath(os.path.dirname(zp), media)
        base = os.path.join(rel, os.path.splitext(os.path.basename(zp))[0])   # _library\Materials.zip -> _library\materials
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                for root in {base, rel, os.path.join("cars", car)}:
                    have[norm(os.path.join(root, n))] = zp
    for f in glob.glob(os.path.join(lib, "**", "*"), recursive=True):
        if os.path.isfile(f):
            have[norm(os.path.relpath(f, media))] = f
    return have


def main(game, car):
    have = index(game, car)
    zp = os.path.join(game, "Mount", "media", "cars", car + ".zip")
    z = zipfile.ZipFile(zp)
    names = {n.lower(): n for n in z.namelist()}
    missing = []
    cb = [n for n in z.namelist() if n.lower().endswith(".carbin")]
    models = set()
    for n in cb:
        r = carbin.parse(z.read(n))
        for _, p in r.lod_masks:
            models.add(p)
        for _, _, p in r.ao_paths:
            if norm(p) not in have:
                missing.append(("ao", n, p))
    for p in sorted(models):
        if norm(p) not in have:
            missing.append(("model", "carbin", p))
    mats = {}
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"):
            continue
        for b in bundle.parse(z.read(n)):
            if b.tag != b"ItaM" or not b.data:
                continue
            for ib in bundle.parse(b.data):
                if ib.tag == b"ITAM" and ib.data:
                    ln = ib.data[0]
                    mats.setdefault(ib.data[1:1 + ln].decode("latin1"), n)
    for p, n in sorted(mats.items()):
        if norm(p) not in have:
            missing.append(("material", n, p))
    print("carbins %d, models %d, materials %d, indexed files %d" % (len(cb), len(models), len(mats), len(have)))
    for kind, src, p in missing:
        print("MISSING %-8s %s   (from %s)" % (kind, p, src))
    print("missing:", len(missing))


if __name__ == "__main__":
    main(*sys.argv[1:])
