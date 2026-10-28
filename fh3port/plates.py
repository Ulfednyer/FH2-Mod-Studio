"""Licence plates: FH2 has none (no plate text system), so FH3's plate models show a row of zeros. By default the
porter hides them: every mesh of the car's plate models (scene/exterior/plate/plateUS_a, plateEU_b, fplateEU_a,
plateManu_a ...) gets LODFlags 0 = never drawn, the way slod.py hides meshes. The files stay, so the carbin entries that
reference them stay valid. Plate lamps (plateLight*) and brackets (plateBracket*) are body parts and are kept.

Usage: py plates.py hide <in.zip> <out.zip>
"""
import re
import struct
import sys
import zipfile

import geom
import ziputil

PLATE = re.compile(r"(?i)(^|/)f?plate(us|eu|uk|jp|manu)_[a-z0-9]+\.modelbin$")


def is_plate(name):
    return bool(PLATE.search(name))


def hide_model(d):
    hsize, ents = geom.read_bundle(d)
    n = 0
    for e in ents:
        if e.tag == "Mesh" and struct.unpack_from("<H", e.data, 4)[0]:
            b = bytearray(e.data)
            struct.pack_into("<H", b, 4, 0)
            e.data = bytes(b)
            n += 1
    return (geom.write_bundle(d, hsize, ents) if n else d), n


def fix_zip(src, dst):
    log = []
    with zipfile.ZipFile(src) as zin, ziputil.writer(dst) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if is_plate(info.filename):
                data, n = hide_model(data)
                if n:
                    log.append("%s: %d meshes hidden" % (info.filename.split("/")[-1], n))
            zout.writestr(info, data)
    return log


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "hide":
        print("\n".join(fix_zip(sys.argv[2], sys.argv[3])) or "no plate models")
    else:
        print(__doc__)
