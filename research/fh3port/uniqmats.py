"""Materials a ported car uses that no other (working) ported car uses, with shader, blob versions and a strict
parameter check. usage: uniqmats.py <car> <working car> [<working car> ...]"""
import os
import sys
import zipfile

sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle
import fh3port as P
import lightparams
import mtpr
from matidump import s7


def mats(car):
    z = zipfile.ZipFile(os.path.join(P.FH2, "cars", car + ".zip"))
    pre = "game:\\media\\cars\\%s" % car.lower()
    out = set()
    for n in z.namelist():
        if n.lower().endswith(".modelbin"):
            for b in bundle.parse(z.read(n)):
                if b.tag == b"ItaM":
                    for ib in bundle.parse(b.data):
                        if ib.tag == b"ITAM":
                            out.add(s7(ib.data, 0)[0].lower().replace(pre, "<car>"))
    return out


def main():
    car, good_cars = sys.argv[1], sys.argv[2:]
    good = set()
    for c in good_cars:
        good |= mats(c)
    uniq = sorted(mats(car) - good)
    print("materials only %s uses: %d" % (car, len(uniq)))
    z = zipfile.ZipFile(os.path.join(P.FH2, "cars", car + ".zip"))
    names = {n.lower(): n for n in z.namelist()}
    res = lightparams.Resolver(names, z.read, car, os.path.join(P.FH2_LIB, "Materials.zip"), P.FH2_SHADERS)
    for m in uniq:
        full = m.replace("<car>", "game:\\media\\cars\\%s" % car.lower())
        md = res.material_bytes(full)
        sp = res.shader_of_material(md) if md else None
        err = ""
        vers = []
        try:
            vers = [(b.tag[::-1].decode("latin1"), b.ver) for b in bundle.parse(md)]
            mtpr.strict_check(md)
        except Exception as e:
            err = "FAIL: %s" % e
        print("  %-48s %-42s %s %s" % (m.split("\\")[-1][:48], (sp or "?").split("\\")[-1][:42], vers, err))


if __name__ == "__main__":
    main()
