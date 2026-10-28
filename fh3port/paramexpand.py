"""FH3 material parameters that FH2 splits into several: colour, gloss and reflectance.

FH3 interior and trim materials set one `ColorColorParam` (Centenario seats: black suede, yellow stitching). FH2's
shaders call that colour `DiffuseColorGroupColorParam` (ch1 interior shaders) or `DiffuseColorA/BColorParam` (masked
ch2 shaders: one colour per mask half), so the FH3 name is ignored and the shader's default colours show (white and
red seats). Likewise `Gloss_floatVal` -> `GlossA/GlossB_floatVal` and `F0Vector4` -> `F0a/F0b`. lightparams.py only
renames 1:1; this step writes the value into every FH2 parameter of the group the resolved shader knows.

Two places:
  * MTPR blobs of materialbins and of material instances in modelbins that set the FH3 name: the FH3 parameter is
    renamed to the first FH2 target and the other targets are appended with the same value.
  * materials the converter rebuilt for an FH2 shader (FH3-only shader) lost the colour altogether
    (suede_custom: fabric_colorlookup -> int_ch2normglossch1maskdiffuse, no colour parameter left): when the FH3
    library material of the same path sets the FH3 parameter and the car's copy sets none of the targets, the targets
    are appended with FH3's value.

Run after mtpr and lightparams (parameters must be FH2 v2.0).
"""
import struct
import zipfile

import fh3lib

import bundle
import carbin
import lightparams
import mtpr

# FH3 hash -> alternatives, best first; each alternative is the list of FH2 hashes that together replace it
GROUPS = {
    0x57C321A6: [[0xF51639BE], [0xEF5CCE09, 0x76BEA808], [0x63040D89], [0x1F3EB7A9]],   # ColorColorParam
    0x5FF94E67: [[0x52E99DA3, 0xB9DE26A0], [0x52E99DA3]],                              # Gloss_floatVal
    0x938926B0: [[0x7B6BB8A5, 0xF5E4BF46], [0x1F9B6488, 0x9114636B]],                  # F0Vector4
}


def _targets(src, shader, present):
    for alt in GROUPS[src]:
        if all(struct.pack("<I", h) in shader for h in alt):
            return [h for h in alt if h not in present]
    return None


def _params(b):
    ps, end = mtpr.parse_params(b, None)
    return ps, end


def expand_blob(b, shader, extra=None):
    """MTPR blob data -> new data (or None). extra: {fh3 hash: (type, payload)} to add when the blob sets none of the
    targets (values from the FH3 library material)."""
    ps, end = _params(b)
    present = {h for _, _, _, _, h, _ in ps}
    out = bytearray(b[:1])
    added = 0
    changed = False
    for start, stop, maj, mn, h, typ in ps:
        raw = b[start:stop]
        if h in GROUPS and struct.pack("<I", h) not in shader:
            t = _targets(h, shader, present)
            if t:
                payload = raw[7:]
                for k, dst in enumerate(t):
                    out += raw[:2] + struct.pack("<I", dst) + raw[6:7] + payload
                    present.add(dst)
                    added += k > 0
                changed = True
                continue
        out += raw
    for src, (maj, mn, typ, payload) in (extra or {}).items():
        if src in present or any(set(alt) & present for alt in GROUPS[src]):
            continue
        t = _targets(src, shader, present)
        if t:
            for dst in t:
                out += bytes([maj, mn]) + struct.pack("<I", dst) + bytes([typ]) + payload
                present.add(dst)
                added += 1
            changed = True
    if not changed:
        return None
    count = b[0] + added
    if count > 255:
        return None
    out[0] = count
    return bytes(out + b[end:])


def _fh3_values(fh3_lib, fh3_names, rel):
    """{fh3 hash: (maj, min, type, payload)} of the GROUPS parameters the FH3 library material sets (as FH2 v2)."""
    n = fh3_names.get(rel)
    if not n:
        return {}
    d = fh3_lib.read(n)
    try:
        blobs = carbin._bundle11_to_blobs(d) if d[4:6] == b"\x01\x01" else bundle.parse(d)
        d, _ = mtpr.rebuild_bundle(bundle.serialize(blobs))
    except Exception:
        return {}
    out = {}
    for tag, ver, e, doff, size in mtpr.blobs(d):
        if tag[::-1] != b"MTPR":
            continue
        b = d[doff:doff + size]
        for start, stop, maj, mn, h, typ in _params(b)[0]:
            if h in GROUPS:
                out[h] = (maj, mn, typ, b[start + 7:stop])
    return out


def _fix_bundle(data, shader_of_blob, extra=None):
    """Bundle bytes -> new bytes or None; shader_of_blob(blob list) gives the shader for its MTPR blobs."""
    blobs = bundle.parse(data)
    shader = shader_of_blob(blobs)
    if not shader:
        return None
    changed = False
    for bl in blobs:
        if bl.tag == b"RPTM":
            new = expand_blob(bl.data, shader, extra)
            if new is not None:
                bl.data = new
                changed = True
    return bundle.serialize(blobs) if changed else None


def fix_zip(src, dst, car_name, materials_zip, shaders_zip, fh3_materials_zip):
    stats = {"instances": 0, "materials": 0, "restored": 0}
    fh3 = fh3lib.LayeredZip(fh3_materials_zip)
    fh3_names = {n.lower(): n for n in fh3.namelist()}
    with zipfile.ZipFile(src) as zin:
        names = {n.lower(): n for n in zin.namelist()}
        res = lightparams.Resolver(names, zin.read, car_name, materials_zip, shaders_zip)

        def shader_from_matl(blobs):
            for bl in blobs:
                if bl.tag == b"LTAM":
                    sp = lightparams._s7(bl.data, 0)[0]
                    return res.shader_bytes(sp)
            return None

        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info)
                low = info.filename.lower()
                new = None
                if low.endswith(".materialbin") and data[4:6] == b"\x01\x00":
                    extra = _fh3_values(fh3, fh3_names, low[len("materials/"):]) if low.startswith("materials/") else {}
                    before = data
                    new = _fix_bundle(data, shader_from_matl, extra)
                    if new is not None:
                        stats["materials"] += 1
                        if any(struct.pack("<I", h) not in before for h in extra):
                            stats["restored"] += 1
                elif low.endswith(".modelbin") and data[4:6] == b"\x01\x00":
                    blobs = bundle.parse(data)
                    changed = False
                    for bl in blobs:
                        if bl.tag != b"ItaM":
                            continue
                        inner = bundle.parse(bl.data)
                        mpath = next((lightparams._s7(ib.data, 0)[0] for ib in inner if ib.tag == b"ITAM"), None)
                        md = res.material_bytes(mpath) if mpath else None
                        sp = res.shader_of_material(md) if md else None
                        shader = res.shader_bytes(sp) if sp else None
                        if not shader:
                            continue
                        hit = False
                        for ib in inner:
                            if ib.tag == b"RPTM":
                                nb = expand_blob(ib.data, shader)
                                if nb is not None:
                                    ib.data = nb
                                    hit = True
                        if hit:
                            bl.data = bundle.serialize(inner)
                            changed = True
                            stats["instances"] += 1
                    if changed:
                        new = bundle.serialize(blobs)
                zout.writestr(info, new if new is not None else data)
    return stats
