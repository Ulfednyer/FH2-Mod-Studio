"""Shaders a ported car's materials use: are their compiled pass files (.vso/.pso) in Shaders.zip, and does any FH2
car use them? usage: shadercheck.py <car> [n_fh2_cars]"""
import collections
import glob
import os
import random
import sys
import zipfile

sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle
import fh3port as P
import lightparams
from matidump import s7


def shaders_of(zp, car):
    z = zipfile.ZipFile(zp)
    names = {n.lower(): n for n in z.namelist()}
    res = lightparams.Resolver(names, z.read, car, os.path.join(P.FH2_LIB, "Materials.zip"), P.FH2_SHADERS)
    out = collections.Counter()
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"):
            continue
        try:
            bl = bundle.parse(z.read(n))
        except ValueError:
            continue
        for b in bl:
            if b.tag != b"ItaM":
                continue
            try:
                inner = bundle.parse(b.data)
            except ValueError:
                continue
            for ib in inner:
                if ib.tag == b"ITAM":
                    md = res.material_bytes(s7(ib.data, 0)[0])
                    sp = res.shader_of_material(md) if md else None
                    if sp:
                        out[sp.split("\\")[-1].lower()] += 1
    return out


def main():
    car = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    sz = zipfile.ZipFile(P.FH2_SHADERS)
    files = collections.defaultdict(list)
    for n in sz.namelist():
        parts = n.lower().split("/")
        if len(parts) >= 2:
            files[parts[-2]].append(parts[-1])
    mine = shaders_of(os.path.join(P.FH2, "cars", car + ".zip"), car)
    zips = [z for z in glob.glob(os.path.join(P.FH2, "cars", "*_*.zip")) if "fh3tire" not in z.lower()]
    j = P.journal()
    ported = {v.get("zip", "").lower() for v in j["cars"].values()}
    zips = [z for z in zips if os.path.relpath(z, P.GAME).lower() not in ported]
    random.seed(1)
    used = collections.Counter()
    for zp in random.sample(zips, min(k, len(zips))):
        used.update(shaders_of(zp, os.path.basename(zp)[:-4]).keys())
    print("%s: %d shaders" % (car, len(mine)))
    for sh, cnt in sorted(mine.items()):
        folder = sh[:-len(".shaderbin")]
        f = files.get(folder, [])
        vso = sum(x.endswith(".vso") for x in f)
        pso = sum(x.endswith(".pso") for x in f)
        print("  %-46s meshes %3d  vso %3d pso %3d  used by %2d of %d FH2 cars" % (sh, cnt, vso, pso, used[sh], k))


if __name__ == "__main__":
    main()
