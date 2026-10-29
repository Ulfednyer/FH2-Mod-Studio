"""Restores the donor's name in carbin AO paths that point into the shared library (game:\\media\\cars\\_library\\...).
The first fh1port renamed the donor in every carbin string, so the wheel AO became
_library\\textures\\libraryao\\wheels\\<new car>_wheellf_ao.swatchbin, which does not exist: the car showed in the
Autoshow list preview, but Buy Car / Color Select stayed black (3D view waiting for the car).

    py aopathfix.py <installed car zip> <new MediaName> <donor MediaName>   (FH2 closed; journal keeps the original)
"""
import os
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "..", "fh3port")))
import carbin
import fh3port


def fix_carbin(d, new, donor):
    r = carbin.parse(d)
    changes = {}
    for off, _, p in r.ao_paths:
        low = p.lower()
        if "\\cars\\_library\\" in low and new.lower() in low:
            changes[off] = low.replace(new.lower(), donor.lower())
    return (carbin.set_ao_paths(d, changes), changes) if changes else (None, {})


def main(zp, new, donor):
    fixed = {}
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            if n.lower().endswith(".carbin"):
                out, changes = fix_carbin(z.read(n), new, donor)
                if out is not None:
                    carbin.parse(out)   # must still parse
                    fixed[n] = out
                    for p in sorted(set(changes.values())):
                        print("  %s: AO -> %s (%d)" % (n, p, list(changes.values()).count(p)))
    if fixed:
        j = fh3port.journal()
        fh3port.replace_in_zip(j, zp, fixed)
        fh3port.save_journal(j)
    print("fixed %d carbins" % len(fixed))


if __name__ == "__main__":
    main(*sys.argv[1:])
