"""FH3 -> FH2 ManufacturerColors.bin (paint list) downgrade.

Bundle with one MNCL blob: u8 groupCount, per group u8 entryCount, per entry
    mask (FH2 blob 1.0: u16, FH3 blob 1.1: u32) | vec3 preview colour | 7-bit-length string materialbin path.
The converter only rewrites the outer bundle header, so FH2 got a 1.1 blob with u32 masks and misread every paint
entry (layout from ForzaTechStudio's ManufacturerColorsBlob, confirmed on FH2/FH3 files).

Usage: py mncl.py fix <in.zip> <out.zip>
"""
import re
import struct
import sys
import zipfile

import fh3lib
import geom


def _str7_end(b, p):
    n = s = 0
    while True:
        c = b[p]; p += 1
        n |= (c & 0x7F) << s; s += 7
        if not c & 0x80:
            return p + n


WARNINGS = []


def downgrade_blob(b):
    out = bytearray(b[:1])
    p = 1
    for _ in range(b[0]):
        cnt = b[p]; out.append(cnt); p += 1
        for _ in range(cnt):
            mask = struct.unpack_from("<I", b, p)[0]; p += 4
            if mask > 0xFFFF:
                # 39 FH3 cars paint a material slot >= 16 (always a single bit); FH2 cannot address it
                WARNINGS.append("paint mask 0x%x has material slots >= 16; kept 0x%x" % (mask, mask & 0xFFFF))
            out += struct.pack("<H", mask & 0xFFFF)
            end = _str7_end(b, p + 12)
            out += b[p:end]; p = end
    if p != len(b):
        raise ValueError("MNCL blob: %d unparsed bytes" % (len(b) - p))
    return bytes(out)


def fix_bytes(d):
    """Returns new bytes, or None when the file already is FH2's format."""
    hsize, ents = geom.read_bundle(d)
    changed = False
    for e in ents:
        if e.tag == "MNCL" and e.ver == (1, 1):
            e.data, e.ver = downgrade_blob(e.data), (1, 0)
            changed = True
    return geom.write_bundle(d, hsize, ents) if changed else None


def _str7(s):
    b = s.encode("latin-1"); out = bytearray(); n = len(b)
    while True:
        c = n & 0x7F; n >>= 7
        out.append(c | (0x80 if n else 0))
        if not n:
            return bytes(out) + b


def paths_blob(b, rename=None):
    """FH2 (1.0) MNCL blob -> list of material paths; with rename(path) -> new path, the rebuilt blob instead."""
    out, paths, p = bytearray(b[:1]), [], 1
    for _ in range(b[0]):
        cnt = b[p]; out.append(cnt); p += 1
        for _ in range(cnt):
            out += b[p:p + 14]; p += 14             # u16 mask + vec3 preview colour
            n = s = 0; q = p
            while True:
                c = b[q]; q += 1; n |= (c & 0x7F) << s; s += 7
                if not c & 0x80:
                    break
            path = b[q:q + n].decode("latin-1"); p = q + n
            paths.append(path)
            out += _str7(rename(path)) if rename else b""
    return bytes(out) if rename else paths


def convert_material(d):
    """FH3 library materialbin (burG 1.1, MTPR v3) -> FH2 (1.0, v2)."""
    import bundle
    import carbin
    import mtpr
    blobs = carbin._bundle11_to_blobs(d) if d[4:6] == b"\x01\x01" else bundle.parse(d)
    out, _ = mtpr.rebuild_bundle(bundle.serialize(blobs))
    mtpr.strict_check(out)
    return out


LIB_PREFIX = "game:\\media\\cars\\_library\\materials\\"


def paint_renames(blob, zip_names, car_name, lib2, z3, lib3):
    """Paints FH2's library lacks (FH3 Aston greens, R8 greens...) render black. Each is copied from FH3's library into
    the car zip as materials/<rel>, converted, the way FH2 itself ships car-only paints (Zagato quantumsilver2).
    Returns ({zip name: bytes} to add, {old path lower: new path})."""
    add, ren = {}, {}
    have = {x.lower() for x in zip_names}
    for path in paths_blob(blob):
        low = path.lower()
        if not low.startswith(LIB_PREFIX) or low in ren:
            continue
        rel = low[len(LIB_PREFIX):].replace("\\", "/")
        if rel in lib2:
            continue
        if rel not in lib3:
            # not shipped by FH3 either (por_hoonigan_91 whitepearlmatte): FH2's closest-named library paint
            import difflib
            folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
            pool = {x.rsplit("/", 1)[-1][:-12]: x for x in lib2 if x.startswith(folder) and x.endswith(".materialbin")}
            near = difflib.get_close_matches(rel.rsplit("/", 1)[-1][:-12], list(pool), 1, 0.5)
            if near:
                ren[low] = LIB_PREFIX + pool[near[0]].replace("/", "\\")
                WARNINGS.append("paint %s is in no FH2 or FH3 library; using FH2's %s" % (rel, pool[near[0]]))
            else:
                WARNINGS.append("paint %s missing in FH2 and FH3 libraries (renders black)" % rel)
            continue
        if "materials/" + rel not in have:
            add["materials/" + rel] = convert_material(z3.read(lib3[rel]))
        ren[low] = "Game:\\Media\\cars\\%s\\materials\\%s" % (car_name.lower(), rel.replace("/", "\\"))
    return add, ren


# Paint shaders only FH3 has -> FH2 shader + parameters to switch on. carpaint_standard_glossmask (race cars' base
# livery: GT-R #1 NISMO, Focus RS RX) is carpaint_standard plus a gloss mask; without the shader FH2 can't build the
# material and the body under the decals renders black. The livery colours come from CH1DiffuseTexture, which
# carpaint_standard only samples with CH1DiffuseTextureSwitchBool on (glossmask always samples it).
PAINT_SHADER_REMAP = {
    "carpaint_standard_glossmask": ("carpaint_standard", [(0x7169AC81, 3, struct.pack("<I", 1))]),
}


def retarget_textures(d, mapping):
    """FH2 (bundle 1.0) materialbin: Texture2D parameters whose path (lower case) is in mapping get the mapped path."""
    import bundle
    import mtpr
    blobs = bundle.parse(d)
    n = 0
    for b in blobs:
        if b.tag != b"RPTM":
            continue
        ps, end = mtpr.parse_params(b.data, None)
        for start, stop, maj, mn, h, t in reversed(ps):
            if t != 6:
                continue
            p = start + 7; ln = s = 0
            while True:
                c = b.data[p]; p += 1; ln |= (c & 0x7F) << s; s += 7
                if not c & 0x80:
                    break
            path = b.data[p:p + ln].decode("latin-1")
            new = mapping.get(path.lower())
            if new:
                b.data = b.data[:start + 7] + _str7(new) + b.data[p + ln:]
                n += 1
    if not n:
        return d
    out = bundle.serialize(blobs)
    mtpr.strict_check(out)
    return out


def closest_texture(path, names):
    """game:\\media\\cars\\_library\\textures\\<dir>\\<name>_<guid>.swatchbin -> the existing library texture in the
    same folder with the closest name (guid ignored), as a game path; names = lower-case paths inside Textures.zip."""
    import difflib
    rel = path.lower().replace("\\", "/").split("_library/textures/", 1)[-1]
    folder, _, fname = rel.rpartition("/")
    stem = lambda f: re.sub(r"_[0-9a-f]{8}-[0-9a-f-]{27}\.swatchbin$|\.swatchbin$", "", f)
    pool = {stem(n.rpartition("/")[2]): n for n in names if n.rpartition("/")[0] == folder}
    near = difflib.get_close_matches(stem(fname), list(pool), 1, 0.5)
    return LIB_TEX_PREFIX + pool[near[0]].replace("/", "\\") if near else None


LIB_TEX_PREFIX = "game:\\media\\cars\\_library\\textures\\"


def remap_paint_shader(d):
    """Paint materialbin (FH2 bundle 1.0) using an FH3-only shader -> FH2 one, or None when nothing to do."""
    import bundle
    import mtpr
    blobs = bundle.parse(d)
    matl = next((b for b in blobs if b.tag == b"LTAM"), None)
    if matl is None:
        return None
    n = s = p = 0
    while True:
        c = matl.data[p]; p += 1; n |= (c & 0x7F) << s; s += 7
        if not c & 0x80:
            break
    path = matl.data[p:p + n].decode("latin-1")
    parts = path.split("\\")
    if len(parts) < 2 or parts[-2].lower() not in PAINT_SHADER_REMAP:
        return None
    new_name, add = PAINT_SHADER_REMAP[parts[-2].lower()]
    new_path = "\\".join(parts[:-2] + [new_name, new_name + ".shaderbin"])
    matl.data = _str7(new_path) + matl.data[p + n:]
    matl.metas = [(t, v, new_name.encode("latin-1") if t == b"emaN" and md.decode("latin-1", "replace").lower() == parts[-2].lower() else md)
                  for t, v, md in matl.metas]
    for b in blobs:
        if b.tag != b"RPTM":
            continue
        ps, end = mtpr.parse_params(b.data, None)
        present = {h for _, _, _, _, h, _ in ps}
        hdr = b.data[ps[0][0]:ps[0][0] + 2] if ps else b"\x02\x00"
        extra = bytearray()
        k = 0
        for h, typ, payload in add:
            if h in present:
                # already set (e.g. switched off): set it on
                for start, stop, maj, mn, hh, t in ps:
                    if hh == h:
                        b.data = b.data[:start + 7] + payload + b.data[stop:]
                        break
                ps, end = mtpr.parse_params(b.data, None)
                continue
            extra += hdr + struct.pack("<I", h) + bytes([typ]) + payload
            k += 1
        if k:
            b.data = bytes([b.data[0] + k]) + b.data[1:end] + bytes(extra) + b.data[end:]
    out = bundle.serialize(blobs)
    mtpr.strict_check(out)
    return out


def fix_zip(src, dst, car_name=None, fh2_lib=None, fh3_lib=None):
    """Downgrades paint lists; with car_name and both library Materials.zip paths also brings in missing paints and
    moves paints off FH3-only shaders."""
    changed = 0
    if car_name and fh2_lib and fh3_lib:
        lib2 = {n.lower() for n in zipfile.ZipFile(fh2_lib).namelist()}
        z3 = fh3lib.LayeredZip(fh3_lib)     # Materials.zip + Materials_pri_44/45.zip
        lib3 = {n.lower(): n for n in z3.namelist()}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        added = {}
        # paints the colour list points at inside the car zip (any of them may use an FH3-only shader)
        paint_paths = set()
        if car_name:
            pre = "game:\\media\\cars\\%s\\" % car_name.lower()
            for info in zin.infolist():
                if info.filename.lower().endswith("manufacturercolors.bin"):
                    d0 = fix_bytes(zin.read(info)) or zin.read(info)
                    for e in geom.read_bundle(d0)[1]:
                        if e.tag == "MNCL":
                            for pth in paths_blob(e.data):
                                if pth.lower().startswith(pre):
                                    paint_paths.add(pth.lower()[len(pre):].replace("\\", "/"))
        remapped = []
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower() in paint_paths and data[4:6] == b"\x01\x00":
                new = remap_paint_shader(data)
                if new is not None:
                    data = new
                    remapped.append(info.filename.split("/")[-1])
            if info.filename.lower().endswith("manufacturercolors.bin"):
                new = fix_bytes(data)
                if new is not None:
                    data = new
                    changed += 1
                if car_name and fh2_lib and fh3_lib:
                    hsize, ents = geom.read_bundle(data)
                    for e in ents:
                        if e.tag != "MNCL":
                            continue
                        add, ren = paint_renames(e.data, zin.namelist(), car_name, lib2, z3, lib3)
                        if ren:
                            e.data = paths_blob(e.data, lambda pth: ren.get(pth.lower(), pth))
                            added.update(add)
                            WARNINGS.append("paints copied from FH3 into the car: " +
                                            ", ".join(sorted(v.split("\\")[-1] for v in ren.values())))
                    data = geom.write_bundle(data, hsize, ents)
            zout.writestr(info, data)
        for name, data in added.items():
            if data[4:6] == b"\x01\x00":
                new = remap_paint_shader(data)
                if new is not None:
                    data = new
                    remapped.append(name.split("/")[-1])
            zout.writestr(name, data)
        if remapped:
            WARNINGS.append("paints moved off FH3-only shaders: " + ", ".join(sorted(remapped)))
    return changed


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "fix":
        print("fixed %d files" % fix_zip(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
