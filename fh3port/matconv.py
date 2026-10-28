"""Convert FH3 materials whose shader FH2 lacks into FH2 materials, and undo the converter's texture swaps.

1. Shader conversion. For an FH3-only shader the converter picks an FH2 shader by name similarity and keeps FH3's
   parameters (or matmap swaps in FH2's same-named library material). Both lose the look: leather and plastic landed on
   FH2's metal shader (int_m_ch2normglossalphaemissive) without their colour, suede on a shader that takes its colour
   from a texture (tan dash), and FH2's same-named materials carry FH2's colours (leather_lgl: light grey 0.64 where
   FH3 has black 0.007) -> white/grey interiors (Zonda R, Centenario, Zenvo ST1, Focus RS RX, ...).
   FH2's own copies of the same library materials show the right targets (research/fh3port/matlearn.py): the FH3
   interior shaders correspond to FH2's ch1/ch2diffnormglossalpha family, metals to FH2's m_ shaders. Here every such
   material gets that FH2 shader (int_ variant for interior folders; m_ variant when FH3's reflectance says metal)
   and FH3's own parameter values under FH2's names (ColorColorParam -> DiffuseColorA/B or DiffuseColorGroup,
   Gloss -> GlossA/B, F0Vector4 -> F0a/F0b, CH1/CH2 diffuse textures -> DiffuseATexture, tiling). Parameters the FH2
   shader doesn't know are dropped; unset ones take the shader's defaults. vlayfix later gives the meshes the vertex
   layout of the new shader.

2. Texture restore. Where FH2 lacks a texture the converter substitutes a similarly named one (defaultch1_nrml ->
   eye_nrml, gascap_018 -> gascap_001, mask_default -> led_001_mask): 125 swaps on the Zonda R, the source of
   patterned and wrongly lit surfaces. The porter copies missing FH3 library textures anyway
   (missing_library_textures), so every swapped cars\\_library or car-own texture goes back to FH3's. Textures of the
   global media\\_library (packed in FH2, not on disk, so the converter can't see them) go back when FH2's own
   materials use the same file (defaultch1_nrml, mask_default_mask ...).
"""
import os
import re
import struct
import zipfile

import bundle
import mtpr
from lightparams import NAMES, _s7, generic_target

LIB_TEX = "game:\\media\\cars\\_library\\textures\\"
GLOBAL_TEX = "game:\\media\\_library\\"
_GLOBAL_RE = re.compile(rb"(?i)game:\\media\\_library\\[\x20-\x7e]+?\.swatchbin")


_global_cache = {}


_GUID = re.compile(r"_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.swatchbin$")


def fh2_global_textures(materials_zips):
    """{lower path: path} of the global-library textures FH2's own materials use (they exist in FH2's packed
    library), plus {guid: path} for FH3 files that are renamed copies (ch1_normao_diffopac_nrml_34b98759... is FH2's
    defaultch1_nrml_34b98759...)."""
    key = tuple(materials_zips)
    if key not in _global_cache:
        paths = {}
        for zp in (p for p in materials_zips if os.path.exists(p)):
            with zipfile.ZipFile(zp) as z:
                for n in z.namelist():
                    for m in _GLOBAL_RE.findall(z.read(n)):
                        paths.setdefault(m.decode("latin1").lower(), m.decode("latin1"))
        guids = {}
        for low, p in paths.items():
            g = _GUID.search(low)
            if g:
                guids.setdefault(g.group(1), p)
        _global_cache[key] = (paths, guids)
    return _global_cache[key]


def resolve_texture(path, car_files, fh2_global):
    """The texture path FH2 can load for an FH3 texture path (the porter copies missing cars\\_library ones), or None."""
    low = path.lower()
    if low.startswith(LIB_TEX):
        return path
    if low.startswith(GLOBAL_TEX):
        paths, guids = fh2_global
        if low in paths:
            return path
        g = _GUID.search(low)
        return guids.get(g.group(1)) if g else None
    return path if low.split("\\", 4)[-1].replace("\\", "/") in car_files else None


def _texture_payload(payload, resolve):
    """Texture parameter payload (str7 path + u32) with the path resolve() gives, or None."""
    path, end = _s7(payload, 0)
    new = resolve(path)
    if new is None:
        return None
    return payload if new == path else _str7(new) + payload[end:]

# FH3 shader -> FH2 family (ch1: one colour, DiffuseColorGroup; ch2: two colours, DiffuseColorA/B)
FAMILY = {
    "int_ch2_simplenormalao_glossvar": "ch2", "w_int_ch2_simplenormalao_glossvar": "ch2",
    "fabric_colorlookup": "ch2", "w_fabric_colorlookup": "ch2",
    "int_simplediffuse": "ch2", "w_int_simplediffuse": "ch2", "ext_simplemetal": "ch2",
    "int_ch2_dualmetal_rtintmap": "ch2",
    "int_ch1_normdiffuseopacity": "ch1", "w_int_ch1_normdiffuseopacity": "ch1",
    "int_ch1_dualsurface_diffuse": "ch1", "int_ch1_dualsurface_simple": "ch1", "w_int_ch1_dualsurface_simple": "ch1",
    "int_ch1_normopacity": "ch1", "fabric_diffusetexture": "ch1", "int_ch1diffusemap": "ch1",
    "int_grille": "ch1", "ext_grille": "ch1",
    "int_ch2_norm_diffuse": "ch1",                       # textured leather (Zenvo ST1 seats): diffuse texture only
    # sun strips: FH2 has no banner shader -> car paint drawing the strip's texture (as for race liveries)
    "car_windsheildbanner": "carpaint_standard", "car_windsheildbanner_livery": "carpaint_standard",
}
# (family, metal, interior) -> FH2 shader
TARGET = {
    ("ch2", False, True): "int_ch2diffnormglossalpha", ("ch2", False, False): "ch2diffnormglossalphaemissive",
    ("ch2", True, True): "int_m_ch2normglossalphaemissive", ("ch2", True, False): "m_ch2normglossalphaemissive",
    ("ch1", False, True): "int_ch1diffnormglossalpha", ("ch1", False, False): "ch1diffnormglossalphaemissive",
    ("ch1", True, True): "int_m_ch1normglossalphaemissive", ("ch1", True, False): "m_ch1normglossalphaemissive",
}
ALWAYS_METAL = {"int_ch2_dualmetal_rtintmap"}

# FH3 parameter name -> alternatives (first whose names the FH2 shader all knows wins), each a list of FH2 names
RENAME = {
    "ColorColorParam": [["DiffuseColorAColorParam", "DiffuseColorBColorParam"], ["DiffuseColorGroupColorParam"]],
    "DiffuseColorGroupColorParam": [["DiffuseColorGroupColorParam"], ["DiffuseColorAColorParam", "DiffuseColorBColorParam"]],
    "Gloss_floatVal": [["GlossA_floatVal", "GlossB_floatVal"], ["GlossA_floatVal"]],
    "GlossA_floatVal": [["GlossA_floatVal", "GlossB_floatVal"], ["GlossA_floatVal"]],
    "F0Vector4": [["F0a", "F0b"], ["F0aVector4", "F0bVector4"], ["F0a"], ["F0aVector4"]],
    "ReflectionTintColorColorParam": [["ReflectionTintColorParam"]],
    "CH1DiffuseTextureTexture": [["DiffuseATexture"]],
    "CH2DiffuseTextureTexture": [["DiffuseATexture"]],
    "CH2DiffuseTexture": [["DiffuseATexture"]],
    "CH2NormalTexture": [["NormalTexture"]],
    "CH2NormalHeightScale": [["NormalHeightScale"]],
    "CH2NormalTiling": [["NormalTiling"]],
    "DiffuseTextureSwitchBool": [["DiffuseTextureSwitchBool"], ["CH1DiffuseTextureSwitchBool"]],
    0x54969DE6: [["DiffuseATiling"]],                    # int_ch2_norm_diffuse: unnamed diffuse tiling
}
# dual-surface shaders (metal and non-metal half): the half that matches the chosen FH2 shader
DUAL = {False: {"F0_NonMetal": "F0Vector4", "Gloss_NonMetal": "Gloss_floatVal"},
        True: {"F0_Metal": "F0Vector4", "Gloss_Metal": "Gloss_floatVal"}}

_BY_NAME = {}
for _h, _n in NAMES.items():
    _BY_NAME.setdefault(_n, []).append(_h)
_F0 = 0x938926B0        # F0Vector4
_METAL_SWITCH = [h for h, n in NAMES.items() if n == "MetalSwitchBool"]


def _hash_in(name, shader):
    return next((h for h in _BY_NAME.get(name, []) if struct.pack("<I", h) in shader), None)


def _params(blob, ver):
    """[(hash, type, payload)] of an MTPR blob (v2 or v3) plus its trailer."""
    ps, end = mtpr.parse_params(blob, ver)
    out = []
    for start, stop, maj, mn, h, typ in ps:
        p = start + 6
        if (maj, mn) >= (3, 1):
            p += 1 + (4 if blob[p] else 0)
        p += 1 + (16 if maj >= 3 else 0)
        payload = blob[p:stop]
        if typ == 7 and len(payload) == 8:
            payload += b"\x00\x00\x00\x00"
        out.append((h, typ, payload))
    return out, blob[end:]


def _mtpr_of(data):
    for tag, ver, _, doff, size in mtpr.blobs(data):
        if tag == b"RPTM":
            return data[doff:doff + size], ver
    return None, None


def _shader_of(data):
    for tag, ver, _, doff, size in mtpr.blobs(data):
        if tag[::-1] == b"MATL":
            return _s7(data, doff)[0].replace("\\", "/").rsplit("/", 1)[-1].lower().replace(".shaderbin", "")
    return None


def is_metal(fh3_shader, params):
    if fh3_shader in ALWAYS_METAL:
        return True
    for h, typ, payload in params:
        if h in _METAL_SWITCH and typ == 3:
            return struct.unpack_from("<i", payload)[0] != 0
    for h, typ, payload in params:
        if h == _F0 and typ == 0:
            return max(struct.unpack_from("<3f", payload)) >= 0.2
    return False


def convert_params(params, shader, metal):
    """FH3 parameters -> [(FH2 hash, type, payload)] for the FH2 shader (bytes of its shaderbin)."""
    named = {}
    for h, typ, payload in params:
        n = NAMES.get(h)
        n = DUAL[metal].get(n, n) if n else n
        if n in DUAL[not metal]:
            continue
        named.setdefault(n or h, (h, typ, payload))
    out, renamed = {}, []
    for key, (h, typ, payload) in named.items():
        known = struct.pack("<I", h) in shader
        if known:
            out[h] = (typ, payload)                              # same name in FH2
        if not known or key in RENAME:                           # renames add the FH2 split (GlossA -> A and B)
            renamed.append((key, h, typ, payload))
    for key, h, typ, payload in renamed:
        for alt in RENAME.get(key, []):
            hs = [_hash_in(n, shader) for n in alt]
            if all(hs):
                for t in hs:
                    out.setdefault(t, (typ, payload))
                break
        else:
            if h in out:
                continue
            if key == "NormalTiling" and typ == 11:              # ch2 shaders tile with two floats
                u, v = _hash_in("uTile_floatVal", shader), _hash_in("vTile_floatVal", shader)
                if u and v:
                    out.setdefault(u, (2, payload[:4]))
                    out.setdefault(v, (2, payload[4:8]))
                    continue
            t = generic_target(h, typ, shader, set(out))
            if t:
                out.setdefault(t, (typ, payload))
    return [(h, typ, payload) for h, (typ, payload) in out.items()]


def build_blob(params, trailer):
    out = bytearray([len(params)])
    for h, typ, payload in params:
        out += bytes([2, 0]) + struct.pack("<I", h) + bytes([typ]) + payload
    return bytes(out) + trailer


def _str7(s):
    b = s.encode("latin1")
    n, out = len(b), bytearray()
    while True:
        c = n & 0x7F
        n >>= 7
        out.append(c | (0x80 if n else 0))
        if not n:
            return bytes(out) + b


class Shaders:
    def __init__(self, shaders_zip):
        self.z = zipfile.ZipFile(shaders_zip)
        self.names = {n.lower().rsplit("/", 1)[-1].replace(".shaderbin", ""): n for n in self.z.namelist()
                      if n.lower().endswith(".shaderbin")}
        self.cache = {}

    def path(self, name):
        return "Game:\\Media\\_library\\shaders\\" + self.names[name].replace("/", "\\")

    def bytes(self, name):
        if name not in self.cache:
            self.cache[name] = self.z.read(self.names[name])
        return self.cache[name]


def convert_material(fh2_data, fh3_data, rel, shaders, resolve=lambda path: path):
    """Converter output (FH2 bundle) + FH3 original -> (new FH2 bundle, FH2 shader) or (None, reason)."""
    s3 = _shader_of(fh3_data)
    fam = FAMILY.get(s3)
    if not fam:
        return None, "FH3 shader %s not handled" % s3
    blob3, ver3 = _mtpr_of(fh3_data)
    params3, trailer = _params(blob3, ver3)
    metal = is_metal(s3, params3)
    interior = rel.lower().startswith(("interior", "wetinterior"))
    target = TARGET.get((fam, metal, interior), fam)              # a family or one fixed FH2 shader
    if target not in shaders.names:
        return None, "FH2 shader %s missing" % target
    params2 = []
    for h, typ, payload in convert_params(params3, shaders.bytes(target), metal):
        if typ == 6:
            payload = _texture_payload(payload, resolve)
            if payload is None:                                     # unloadable texture -> the shader's default
                continue
        params2.append((h, typ, payload))
    blobs = bundle.parse(fh2_data)
    for b in blobs:
        if b.tag[::-1] == b"MATL":
            b.data = _str7(shaders.path(target))
        elif b.tag == b"RPTM":
            b.data, b.ver = build_blob(params2, trailer), (2, 0)
    return bundle.serialize(blobs), target


def restore_textures(fh2_data, fh3_data, resolve):
    """Texture parameters of fh2_data that the converter swapped -> FH3's texture (same parameter hash), when FH2 can
    load it (resolve_texture). Returns (data, swaps)."""
    blob3, ver3 = _mtpr_of(fh3_data)
    if blob3 is None:
        return fh2_data, []
    want = {}
    for h, typ, payload in _params(blob3, ver3)[0]:
        if typ == 6:
            want[h] = payload
    blobs = bundle.parse(fh2_data)
    swaps = []
    for b in blobs:
        if b.tag != b"RPTM":
            continue
        params, trailer = _params(b.data, b.ver)
        changed = False
        for i, (h, typ, payload) in enumerate(params):
            if typ != 6 or h not in want:
                continue
            new = _texture_payload(want[h], resolve)
            if new is None or new == payload:
                continue
            swaps.append((NAMES.get(h, hex(h)), _s7(payload, 0)[0].rsplit("\\", 1)[-1], _s7(new, 0)[0].rsplit("\\", 1)[-1]))
            params[i] = (h, typ, new)
            changed = True
        if changed:
            b.data, b.ver = build_blob(params, trailer), (2, 0)
    return (bundle.serialize(blobs), swaps) if swaps else (fh2_data, [])


def fix_zip(src, dst, fh3_car_zip, fh3_materials_zip, shaders_zip, fh2_materials_zips, remaps):
    """remaps: [(rel, fh3 shader, converter shader, score)] from the converter report. Converts the remapped materials
    FAMILY covers and restores swapped textures everywhere. Returns (log lines, set of converted rels)."""
    shaders = Shaders(shaders_zip)
    fh2_global = fh2_global_textures(fh2_materials_zips)
    z3 = zipfile.ZipFile(fh3_car_zip)
    lib = zipfile.ZipFile(fh3_materials_zip)
    n3 = {n.lower(): n for n in z3.namelist()}
    nl = {n.lower(): n for n in lib.namelist()}

    def fh3_source(name):
        k = name.lower()
        if k in n3:
            return z3.read(n3[k])
        if k.startswith("materials/") and k[10:] in nl:
            return lib.read(nl[k[10:]])
        return None

    remapped = {("materials/" + r).lower(): (r, a) for r, a, _, _ in remaps}
    log, converted, swapped = [], set(), 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        car_files = {n.lower() for n in zin.namelist()}
        resolve = lambda path: resolve_texture(path, car_files, fh2_global)
        for info in zin.infolist():
            data = zin.read(info)
            key = info.filename.lower()
            if key.endswith(".materialbin"):
                fh3 = fh3_source(info.filename)
                if fh3 is not None:
                    try:
                        if key in remapped:
                            new, why = convert_material(data, fh3, remapped[key][0], shaders, resolve)
                            if new:
                                data = new
                                converted.add(remapped[key][0].lower())
                                log.append("%s (%s) -> FH2 %s" % (remapped[key][0], remapped[key][1], why))
                        data, swaps = restore_textures(data, fh3, resolve)
                        swapped += len(swaps)
                    except (mtpr.ParseError, ValueError, struct.error) as e:
                        log.append("WARNING %s: %s" % (info.filename, e))
            zout.writestr(info, data)
    log.append("textures restored to FH3's: %d" % swapped)
    return log, converted
