"""Rename FH3 light parameters to FH2's names (car lights stay off otherwise).

Shader parameters are identified by 32-bit name hashes (names from ForzaTechStudio's NameHashService). FH3's light
shaders use other names than FH2's for the same settings, e.g. the NSX taillight instance sets
`Light Parameter` = 69 (FH3) where FH2's Huracan sets `LightFunctionCarLightParam` = 69. An FH2 shader ignores the
FH3 names, so the light function, glow colour and light mask never reach it and the lights stay black.

For every MTPR blob (materialbins and the material instances nested in modelbins) the FH2 shader it ends up on is
resolved (instance -> materialbin -> MATL shader path -> Shaders.zip). A parameter is renamed FH3 -> FH2 only when
that shader does not know the FH3 name, does know the FH2 name, and the blob doesn't already set the FH2 name.
Type and payload stay the same, so only the 4-byte hash changes (in place, no layout change).

Run after mtpr.fix_zip (parameters must be FH2 v2.0).
"""
import struct
import zipfile
import zlib

import mtpr


def crc(name):
    return zlib.crc32(name.encode())


# (FH3 hash, FH2 hash, names). Raw hashes: FH3 ones as set by the NSX's light instances, FH2 ones as set by FH2's
# Huracan taillight (names from ForzaTechStudio's table, which is not pure CRC-32 - so no computing from names).
# First matching source per FH2 parameter wins (order matters for the colours).
RENAME_H = [
    (0x19416CFE, 0x493073A0, "Light Parameter", "LightFunctionCarLightParam"),
    (0x312DBAD1, 0x35C82561, "CH1LightMap", "LightMapTexture"),
    (0x448306EA, 0xC308C931, "LightColor", "IlluminationColoColorParam"),
    (0x796E7357, 0xC308C931, "Headlight_Color", "IlluminationColoColorParam"),
    (0x042FC883, 0xC308C931, "DTRL_Color", "IlluminationColoColorParam"),
]


import json
import os
import re
import ziputil

# Generic renames: FH3 often names a parameter with a type suffix where FH2 doesn't (or the other way round), e.g.
# reflectance `F0aVector4`/`F0bVector4` (FH3) vs `F0a`/`F0b` (FH2 ch1/ch2diffnormglossalphaemissive) - without it
# black plastics and painted metal render without any reflection (flat black). Names: paramnames.json (FTS table).
_SUFFIX = re.compile(r"(Vector4|Vector2|_floatVal|ColorParam|SwitchBool|Bool|Texture|Param)$")
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "paramnames.json"), encoding="utf-8") as _f:
        NAMES = {int(h, 16): n for h, n in json.load(_f)["names"].items()}
except OSError:
    NAMES = {}
_BY_BASE = {}
for _h, _n in NAMES.items():
    _BY_BASE.setdefault(_SUFFIX.sub("", _n).lower(), []).append(_h)


# parameter type (MTPR type byte) -> name suffixes that would contradict it
_WRONG_SUFFIX = {
    0: re.compile(r"(Texture|Map|_floatVal|Bool|Tiling)$"),          # Vector
    1: re.compile(r"(Texture|Map|_floatVal|Bool|Vector4|Tiling)$"),   # Color
    2: re.compile(r"(Texture|Map|Bool|Vector4|ColorParam|Tiling)$"),  # Float
    3: re.compile(r"(Texture|Map|_floatVal|Vector4|ColorParam)$"),    # Bool
    6: re.compile(r"(_floatVal|Bool|Vector4|ColorParam|Tiling)$"),    # Texture2D
    11: re.compile(r"(Texture|Map|_floatVal|Bool|Vector4|ColorParam)$"),  # Vector2
}


def generic_target(h, typ, shader, present):
    """FH2 hash for FH3 hash h: same base name (type suffix ignored), suffix compatible with the parameter type,
    known to the shader, not yet set; else None."""
    name = NAMES.get(h)
    if not name:
        return None
    wrong = _WRONG_SUFFIX.get(typ)
    cands = [c for c in _BY_BASE.get(_SUFFIX.sub("", name).lower(), [])
             if c != h and c not in present and struct.pack("<I", c) in shader
             and not (wrong and wrong.search(NAMES[c]))]
    return cands[0] if len(cands) == 1 else None


def _s7(b, p):
    n = s = 0
    while True:
        c = b[p]; p += 1
        n |= (c & 0x7F) << s; s += 7
        if not c & 0x80:
            return b[p:p + n].decode("latin1"), p + n


class Resolver:
    def __init__(self, car_zip_names, car_reader, car_name, materials_zip, shaders_zip):
        self.car_names, self.car_read, self.car = car_zip_names, car_reader, car_name.lower()
        self.mat = zipfile.ZipFile(materials_zip)
        self.mat_names = {n.lower(): n for n in self.mat.namelist()}
        self.sh = zipfile.ZipFile(shaders_zip)
        self.sh_names = {n.lower(): n for n in self.sh.namelist()}
        self.cache = {}

    def material_bytes(self, path):
        p = path.lower().replace("\\", "/")
        pre = "game:/media/cars/%s/" % self.car
        if p.startswith(pre):
            n = self.car_names.get(p[len(pre):])
            return self.car_read(n) if n else None
        pre = "game:/media/cars/_library/materials/"
        if p.startswith(pre):
            n = self.mat_names.get(p[len(pre):])
            return self.mat.read(n) if n else None
        return None

    def shader_of_material(self, data):
        for tag, ver, ep, doff, size in mtpr.blobs(data):
            if tag[::-1] == b"MATL":
                return _s7(data, doff)[0]
        return None

    def shader_bytes(self, shader_path):
        if shader_path not in self.cache:
            p = shader_path.lower().replace("\\", "/")
            pre = "game:/media/_library/shaders/"
            n = self.sh_names.get(p[len(pre):]) if p.startswith(pre) else None
            self.cache[shader_path] = self.sh.read(n) if n else None
        return self.cache[shader_path]


def _rename_blob(buf, doff, size, shader, stats):
    b = bytes(buf[doff:doff + size])
    params, _ = mtpr.parse_params(b, None)
    present = {h for _, _, _, _, h, _ in params}
    for start, end, maj, mn, h, typ in params:
        if struct.pack("<I", h) in shader:
            continue
        done = False
        for src, dst, a, bname in RENAME_H:
            if h != src or dst in present:
                continue
            if struct.pack("<I", dst) not in shader:
                continue
            struct.pack_into("<I", buf, doff + start + 2, dst)
            present.add(dst)
            stats[a + " -> " + bname] = stats.get(a + " -> " + bname, 0) + 1
            done = True
            break
        if not done:
            dst = generic_target(h, typ, shader, present)
            if dst is not None:
                struct.pack_into("<I", buf, doff + start + 2, dst)
                present.add(dst)
                key = "%s -> %s" % (NAMES[h], NAMES[dst])
                stats[key] = stats.get(key, 0) + 1


def fix_material(data, res, stats):
    """Top-level materialbin: its own MATL decides the shader."""
    sp = res.shader_of_material(data)
    shader = res.shader_bytes(sp) if sp else None
    if not shader:
        return None
    buf = bytearray(data)
    for tag, ver, ep, doff, size in mtpr.blobs(data):
        if tag[::-1] == b"MTPR":
            _rename_blob(buf, doff, size, shader, stats)
    return bytes(buf) if buf != data else None


def fix_model(data, res, stats):
    """Modelbin: each MatI holds a nested bundle (MATI path + MTPR overrides)."""
    buf = bytearray(data)
    for tag, ver, ep, doff, size in mtpr.blobs(data):
        if tag[::-1] != b"MatI":
            continue
        inner = data[doff:doff + size]
        mpath = None
        for t2, v2, e2, d2, s2 in mtpr.blobs(inner):
            if t2[::-1] == b"MATI":
                mpath = _s7(inner, d2)[0]
        mdata = res.material_bytes(mpath) if mpath else None
        sp = res.shader_of_material(mdata) if mdata else None
        shader = res.shader_bytes(sp) if sp else None
        if not shader:
            continue
        for t2, v2, e2, d2, s2 in mtpr.blobs(inner):
            if t2[::-1] == b"MTPR":
                _rename_blob(buf, doff + d2, s2, shader, stats)
    return bytes(buf) if buf != data else None


def fix_zip(src, dst, car_name, materials_zip, shaders_zip):
    stats = {}
    with zipfile.ZipFile(src) as zin:
        names = {n.lower(): n for n in zin.namelist()}
        res = Resolver(names, zin.read, car_name, materials_zip, shaders_zip)
        with ziputil.writer(dst) as zout:
            for info in zin.infolist():
                data = zin.read(info)
                low = info.filename.lower()
                new = None
                if low.endswith(".materialbin"):
                    new = fix_material(data, res, stats)
                elif low.endswith(".modelbin"):
                    new = fix_model(data, res, stats)
                zout.writestr(info.filename, new if new is not None else data)
    return stats
