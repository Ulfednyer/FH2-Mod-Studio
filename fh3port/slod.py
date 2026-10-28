"""LOD fix-ups so FH2 draws what FH3 draws (missing grilles / radiators) and nothing it can't (radiosity z-fighting).

Mesh blob (1.7): i16 material, i16 bone, u16 LODFlags, u8 lastLOD, u8 firstLOD. LODFlags bit 0 = LOD S, bit 1 = LOD0,
bits 2..6 = LOD1..5; lastLOD/firstLOD = highest/lowest LOD index drawn, 255 = S (FH2 examples: S only 0x1/255/255,
S+LOD0 0x3/0/255, S..LOD1 0x7/1/255, LOD1..3 0x1c/3/1). Carbin model entries carry a u16 mask of the LODs a model has.

FH3 draws LOD S for the player car in normal play; FH2 only in panel-open close-ups (Autoshow and driving use LOD0+).
FH2 itself keeps only hidden parts in `__SLOD` models (trunk bay, hood liner, door jambs), always next to a regular
sibling. FH3 also puts visible parts there:
  * honeycomb grilles exist ONLY as `…Honeycomb_a__SLOD` (no sibling)      -> every LOD: 0x7f / 5 / 255, carbin 0x7f
  * the NSX front bay (`BumperF/trunkBay_a__SLOD`) holds the radiators/intercooler seen through the grilles,
    engine/storage/liners likewise (regular sibling exists)                 -> S..LOD1: 0x7 / 1 / 255, carbin 0x7
Only meshes that are S-only (flags 0x1) in exterior `__SLOD` models are changed.

Radiosity: FH3's `materials/radiosity/rad_*` meshes are glow overlays lying exactly on the light housings, drawn with
an FH3-only shader. FH2 has none (matmap makes them clear glass) and they z-fight with the housing -> LODFlags 0
(never drawn).

Run after geom (Mesh 1.7) and carbin.
"""
import struct
import zipfile

import carbin
import geom

# Radiosity meshes turned out to be the lamp reflectors themselves (black lamps when hidden); the flicker was coplanar
# LED/glass and LED/LED layers, handled by zfight.py. matmap now gives them FH2 chrome/plastic/glass instead.
HIDE_RADIOSITY = False

ALL = (0x7F, 5, 255)
NEAR = (0x07, 1, 255)


def _s7(b, p):
    n = s = 0
    while True:
        c = b[p]; p += 1
        n |= (c & 0x7F) << s; s += 7
        if not c & 0x80:
            return b[p:p + n].decode("latin1"), p + n


def slod_targets(names):
    """{zip name: (flags, last, first)} for exterior __SLOD models."""
    low = {n.lower() for n in names}
    out = {}
    for n in names:
        l = n.lower()
        if l.endswith("__slod.modelbin") and "/exterior/" in l:
            out[n] = NEAR if l.replace("__slod", "") in low else ALL
    return out


def material_paths(ents):
    out = {}
    for e in ents:
        if e.tag == "MatI":
            try:
                hs, inner = geom.read_bundle(e.data)
            except geom.GeomError:
                continue
            for b in inner:
                if b.tag == "MATI":
                    out[geom.blob_id(e)] = _s7(b.data, 0)[0].lower()
    return out


def fix_model(d, promote):
    hsize, ents = geom.read_bundle(d)
    mats = material_paths(ents)
    promoted = hidden = 0
    for e in ents:
        if e.tag != "Mesh":
            continue
        mid = struct.unpack_from("<h", e.data, 0)[0]
        flags = struct.unpack_from("<H", e.data, 4)[0]
        b = None
        if HIDE_RADIOSITY and "\\radiosity\\" in mats.get(mid, "") and flags:
            b = bytearray(e.data); struct.pack_into("<H", b, 4, 0); hidden += 1
        elif promote and flags == 0x1:
            b = bytearray(e.data); struct.pack_into("<HBB", b, 4, *promote); promoted += 1
        if b is not None:
            e.data = bytes(b)
    if not (promoted or hidden):
        return d, 0, 0
    return geom.write_bundle(d, hsize, ents), promoted, hidden


def fix_zip(src, dst, car_name):
    log = []
    total_hidden = 0
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        todo = slod_targets(names)
        masks = {}
        for n, pr in todo.items():
            masks[("game:\\media\\cars\\%s\\%s" % (car_name, n.replace("/", "\\"))).lower()] = pr[0]
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info)
                low = info.filename.lower()
                if low.endswith(".modelbin"):
                    data, p, h = fix_model(data, todo.get(info.filename))
                    total_hidden += h
                    if p:
                        log.append("%s: %d meshes LOD S -> 0x%x" % (info.filename.split("/")[-1], p, todo[info.filename][0]))
                elif low.endswith(".carbin") and masks:
                    for mask in sorted(set(masks.values())):
                        data, k = carbin.set_lod_masks(data, {p for p, m in masks.items() if m == mask}, 0x1, mask)
                        log.append("carbin: %d entries mask 0x1 -> 0x%x" % (k, mask))
                zout.writestr(info.filename, data)
    if total_hidden:
        log.append("radiosity meshes hidden: %d" % total_hidden)
    return log
