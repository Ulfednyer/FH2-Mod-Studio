"""
prepatch.py - Pre-processing normalizer for FH3 car zips before ForzaToolsCli.exe fix-materials.

Fixes three main classes of conversion blockers:
1. 0-byte MatI (ItaM) blobs in .modelbin files: populates them with valid burG 1.1 material instances.
2. Missing FH3 library material references: rewrites unresolvable developer/missing materials
   (default.materialbin, debug/boing.materialbin, emergency_lighting*, plastic_normalhack, missing badges)
   to valid FH3 library donor materials.
3. Media library textures referenced in materials/carcolors/*.materialbin: bundles missing textures from
   FH3's media/_library/Textures.zip into textures/<rel> inside the car zip.
4. Strips car-local custom shaders/materials that cannot be converted to FH2.
"""

import os
import re
import struct
import zipfile

import fh3lib
import ziputil

# car-local paint folders the manufacturer colour list points into (SUB_BRATHE_81 keeps its paints in carliveries/)
PAINT_DIRS = ("materials/carcolors/", "materials/carliveries/")
# ... and any other car-local material the car's ManufacturerColors.bin names (Tatuus Fortuna materials/livery/,
# Porsche 944 materials/basematerials/, Holden VK and Regalia materials/, Hoonigan Nova materials/mfr_badges/)
PAINT_REF = re.compile(rb"(?i)game:\\media\\cars\\(?!_library\\)[^\\]+\\(materials\\[\x20-\x7e]+?\.materialbin)")


def paint_files(zin):
    """Lower-case zip names of the car-local materials its paint list points at."""
    out = set()
    for n in zin.namelist():
        if n.lower() == "manufacturercolors.bin":
            out |= {m.group(1).decode("latin-1").lower().replace("\\", "/") for m in PAINT_REF.finditer(zin.read(n))}
    return out

SWATCH_RE = re.compile(rb'([a-zA-Z0-9_\-\\/]+\.swatchbin)', re.I)


def make_fallback_mati(path, name):
    """Creates a valid burG 1.1 material instance bundle (ITAM v1.0 + empty RPTM v2.0)."""
    p_bytes = path.encode("latin1")
    n_bytes = name.encode("latin1")
    itag_data = bytes([len(p_bytes)]) + p_bytes
    npad = (len(n_bytes) + 3) & ~3
    meta_payload = n_bytes + bytes(npad - len(n_bytes)) + b"\x0d\x00\x00\x00"
    mo = 20 + 24 * 2
    meta_table = bytearray(16)
    struct.pack_into("<4sHH", meta_table, 0, b"emaN", (len(n_bytes) << 4) | 0, 16)
    struct.pack_into("<4sHH", meta_table, 8, b"TSTA", (2 << 4) | 1, 16 + npad)
    meta_area = bytes(meta_table) + meta_payload
    hsize = mo + len(meta_area)
    pos = (hsize + 3) & ~3
    out = bytearray(mo)
    struct.pack_into("<4sBBHIII", out, 0, b"burG", 1, 1, 0, hsize, 0, 2)
    # Entry 0: ITAM
    struct.pack_into("<4sBBHIIII", out, 20, b"ITAM", 1, 0, 2, mo, pos, len(itag_data), len(itag_data))
    pos += len(itag_data)
    pos = (pos + 3) & ~3
    # Entry 1: RPTM
    rptm_data = b"\x00" + b"\x00" * 12
    struct.pack_into("<4sBBHIIII", out, 44, b"RPTM", 2, 0, 0, mo + len(meta_area), pos, len(rptm_data), len(rptm_data))
    pos += len(rptm_data)
    pos = (pos + 3) & ~3
    struct.pack_into("<I", out, 12, pos)
    out += meta_area
    out += bytes(((hsize + 3) & ~3) - len(out))
    out += itag_data
    out += bytes(((len(out) + 3) & ~3) - len(out))
    out += rptm_data
    out += bytes(((len(out) + 3) & ~3) - len(out))
    return bytes(out)


def rebuild_nested_burg(d, new_itam_path):
    """Replaces the ITAM material path in a nested material instance bundle."""
    maj, min = d[4], d[5]
    is_11 = (maj, min) == (1, 1)
    off = 20 if is_11 else 16
    count = struct.unpack_from("<I" if is_11 else "<H", d, 16 if is_11 else 6)[0]
    hsize = struct.unpack_from("<I", d, 8)[0]
    blobs = []
    p_bytes = new_itam_path.encode("latin1")
    new_itam_data = bytes([len(p_bytes)]) + p_bytes
    for i in range(count):
        tag, vmaj, vmin, mc, mo, do, sz, usz = struct.unpack_from("<4sBBHIIII", d, off + 24 * i)
        if tag in (b"ITAM", b"TAMB"):
            blobs.append(new_itam_data)
        else:
            blobs.append(d[do:do + sz])
    out = bytearray(d[:hsize])
    pos = (hsize + 3) & ~3
    out += bytes(pos - hsize)
    for i in range(count):
        bdata = blobs[i]
        struct.pack_into("<III", out, off + 24 * i + 12, pos, len(bdata), len(bdata))
        out += bdata
        pos += len(bdata)
        pad = ((pos + 3) & ~3) - pos
        out += bytes(pad)
        pos += pad
    struct.pack_into("<I", out, 12, len(out))
    return bytes(out)


def choose_donor(cur_path, model_name=""):
    """Chooses a valid FH3 library donor material for an unresolvable reference."""
    low = cur_path.lower().replace("\\", "/")
    if "emergency_lighting_glass" in low:
        return "Game:\\Media\\cars\\_library\\materials\\exterior_glass\\gls_clear.materialbin"
    if "emergency_lighting" in low or "hazard_bar" in low:
        return "Game:\\Media\\cars\\_library\\materials\\exterior_lights\\lights_smooth_ch1.materialbin"
    if "plastic_normalhack" in low:
        return "Game:\\Media\\cars\\_library\\materials\\interior_plastic\\plastic.materialbin"
    if any(k in low for k in ("schroth", "599xx", "ferrari_002", "seatbelt", "fabric")):
        return "Game:\\Media\\cars\\_library\\materials\\interior_fabric\\seat_belt_002.materialbin"
    if "cystalf0" in low or ("glass" in low and "interior" in low):
        return "Game:\\Media\\cars\\_library\\materials\\interior_glass\\gls_windsheild_interior.materialbin"
    if "por_944_livery" in low or "livery" in model_name.lower():
        return "Game:\\Media\\cars\\_library\\materials\\exterior_misc\\carPaint.materialbin"
    if "default.materialbin" in low or "debug/boing" in low:
        if "livery" in model_name.lower() or "paint" in low:
            return "Game:\\Media\\cars\\_library\\materials\\exterior_misc\\carPaint.materialbin"
        return "Game:\\Media\\cars\\_library\\materials\\specificuse\\frame.materialbin"
    if any(k in low for k in ("badge", "emblem", "sticker", "logo", "215i_001", "fsport")):
        return "Game:\\Media\\cars\\_library\\materials\\mfr_badges\\for_badge_001.materialbin"
    return "Game:\\Media\\cars\\_library\\materials\\specificuse\\frame.materialbin"


def fix_modelbin(d, fh3_lib_mats, model_name=""):
    """Fills 0-byte ItaM blobs and rewrites missing ITAM references in a burG 1.1 modelbin."""
    maj, min = d[4], d[5]
    if (maj, min) != (1, 1):
        return d
    pad, hsize, tsize, count = struct.unpack_from("<HIII", d, 6)
    blobs_data = []
    has_fix = False
    for i in range(count):
        tag, vmaj, vmin, mc, mo, do, sz, usz = struct.unpack_from("<4sBBHIIII", d, 20 + 24 * i)
        if tag == b"ItaM":
            if sz == 0:
                name = ""
                for k in range(mc):
                    mt, sv, rel = struct.unpack_from("<4sHH", d, mo + 8 * k)
                    if mt == b"emaN":
                        name = d[mo + 8 * k + rel:mo + 8 * k + rel + (sv >> 4)].decode("latin1", errors="replace").rstrip("\x00")
                if "glass" in name.lower():
                    blobs_data.append(make_fallback_mati("Game:\\Media\\cars\\_library\\materials\\exterior_glass\\gls_clear.materialbin", "ClearGlass"))
                else:
                    blobs_data.append(make_fallback_mati("Game:\\Media\\cars\\_library\\materials\\specificuse\\frame.materialbin", "frame"))
                has_fix = True
            else:
                mati = d[do:do + sz]
                is_11 = mati[4:6] == b"\x01\x01"
                mcount = struct.unpack_from("<I" if is_11 else "<H", mati, 16 if is_11 else 6)[0]
                moff = 20 if is_11 else 16
                cur_path = ""
                for j in range(mcount):
                    ntag, nvmaj, nvmin, nmc, nmo, ndo, nsz, nusz = struct.unpack_from("<4sBBHIIII", mati, moff + 24 * j)
                    if ntag in (b"ITAM", b"TAMB") and nsz > 1:
                        slen = mati[ndo]
                        cur_path = mati[ndo + 1:ndo + 1 + slen].decode("latin1", errors="replace")
                norm = cur_path.lower().replace("\\", "/")
                rel = norm.split("materials/", 1)[-1] if "materials/" in norm else norm
                if ".materialbin" in norm and rel not in fh3_lib_mats:
                    donor = choose_donor(cur_path, model_name)
                    new_mati = rebuild_nested_burg(mati, donor)
                    blobs_data.append(new_mati)
                    has_fix = True
                else:
                    blobs_data.append(mati)
        else:
            blobs_data.append(d[do:do + sz])
    if not has_fix:
        return d
    out = bytearray(d[:hsize])
    pos = (hsize + 3) & ~3
    out += bytes(pos - hsize)
    for i in range(count):
        bdata = blobs_data[i]
        struct.pack_into("<III", out, 20 + 24 * i + 12, pos, len(bdata), len(bdata))
        out += bdata
        pos += len(bdata)
        pad_bytes = ((pos + 3) & ~3) - pos
        out += bytes(pad_bytes)
        pos += pad_bytes
    struct.pack_into("<I", out, 12, len(out))
    return bytes(out)


_media_tex_cache = None


def load_media_textures(fh3_root):
    global _media_tex_cache
    if _media_tex_cache is None:
        _media_tex_cache = {}
        # media/_library/Textures.zip and its _pri_ patch zips, in every FH3 media folder (fh3lib.ROOTS)
        for zp in reversed(fh3lib.layers(os.path.join(fh3_root, "_library", "Textures.zip"))):
            with zipfile.ZipFile(zp) as z:
                for n in z.namelist():
                    _media_tex_cache[n.lower().replace("\\", "/")] = (n, zp)    # higher priority overwrites
    return _media_tex_cache


_fh3_lib_mats_cache = None
_car_lib_tex = None


def load_car_library_textures(fh3_lib):
    """FH3 cars/_library/Textures.zip with its _pri_ zips in every media folder (names only until read)."""
    global _car_lib_tex
    if _car_lib_tex is None:
        _car_lib_tex = fh3lib.LayeredZip(os.path.join(fh3_lib, "Textures.zip"))
    return _car_lib_tex


def load_fh3_lib_mats(fh3_lib):
    global _fh3_lib_mats_cache
    if _fh3_lib_mats_cache is None:
        zp = os.path.join(fh3_lib, "Materials.zip")
        with fh3lib.LayeredZip(zp) as z:
            _fh3_lib_mats_cache = {n.lower().replace("\\", "/"): n for n in z.namelist()}
    return _fh3_lib_mats_cache


# FH3-only paint shaders the converter rejects ("shader ... does not exist in FH2" -> unresolved refs, no zip). Car-local
# paints using them (Hoonigan / race base liveries: carpaint_standard_glossmask) are kept out of the converter's input
# and added back afterwards via mncl.convert_material + mncl.remap_paint_shader (fh3port.convert_zip).
HELD_SHADERS = (b"carpaint_standard_glossmask",)
# ... and paints referencing textures that exist nowhere ({zip name: [texture paths]}, filled by prepare_zip); after
# the converter their textures are pointed at the closest-named library texture (mncl.retarget_textures)
MISSING_TEXTURES = {}


def prepare_zip(src_zip, car_name, dst_zip, fh3_lib, fh3_root):
    """Produces a pre-patched car zip ready for ForzaToolsCli.exe fix-materials. Returns {zip name: FH3 bytes} of the
    paints held back from the converter (HELD_SHADERS)."""
    held = {}
    fh3_lib_mats = load_fh3_lib_mats(fh3_lib)
    media_tex = load_media_textures(fh3_root)
    
    extra_textures = {}
    MISSING_TEXTURES.clear()
    with zipfile.ZipFile(src_zip) as zin:
        paints = paint_files(zin)
        car_names = {n.lower() for n in zin.namelist()}

        def is_paint(fn):
            return fn.endswith(".materialbin") and (fn.startswith(PAINT_DIRS) or fn in paints)

        for info in zin.infolist():
            if is_paint(info.filename.lower()):
                d = zin.read(info)
                for m in SWATCH_RE.finditer(d):
                    s = m.group(1).replace(bytes([92]), b"/").decode("latin1").lower()
                    rel = s.split("textures/", 1)[-1]
                    if rel in media_tex:
                        orig_name, zp = media_tex[rel]
                        with zipfile.ZipFile(zp) as ztex:
                            extra_textures["textures/" + orig_name] = ztex.read(orig_name)
                    elif "_library/textures/" in s or "/" in rel:
                        # FH3's car library (cars/_library/Textures*.zip): Porsche 944 emblem, Regalia carbon flake
                        cars_tex = load_car_library_textures(fh3_lib)
                        if rel in cars_tex.index:
                            if "textures/" + rel not in extra_textures:
                                extra_textures["textures/" + cars_tex.index[rel][1]] = cars_tex.read(rel)
                        elif "textures/" + rel not in car_names:
                            # shipped nowhere (FH3's own Regalia blackredflake carbonfiber_011_diff/_rtint)
                            MISSING_TEXTURES.setdefault(info.filename, []).append(m.group(1).decode("latin1"))

    with zipfile.ZipFile(src_zip) as zin, ziputil.writer(dst_zip) as zout:
        for info in zin.infolist():
            fn = info.filename.lower()
            # Strip car-local custom shaders/materials that cannot convert to FH2
            if fn.startswith(("shaders/", "materials/")) and not fn.startswith(PAINT_DIRS) and fn not in paints:
                continue
            d = zin.read(info)
            if is_paint(fn) and (any(h in d.lower() for h in HELD_SHADERS) or info.filename in MISSING_TEXTURES):
                held[info.filename] = d
                continue
            if info.filename.endswith(".modelbin"):
                d = fix_modelbin(d, fh3_lib_mats, info.filename)
            zout.writestr(info.filename, d)
        for tpath, tbytes in extra_textures.items():
            zout.writestr(tpath, tbytes)
    return held
