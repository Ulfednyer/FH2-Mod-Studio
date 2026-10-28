"""Replace converter-remapped FH3 materials with real FH2 library materials.

When an FH3 material's shader does not exist in FH2, the converter swaps in "the closest" FH2 shader by a name score
and keeps FH3's parameters. The FH2 shader then misses its own parameters/textures and renders flat black (NSX
lights, interior). Instead, the bundled materialbin (materials/<folder>/<name>.materialbin in the car zip) is
overwritten with a complete FH2 material (FH2 shader + FH2 parameters + FH2 library textures), keeping its path so
no model has to change. Material-instance overrides in the modelbins still apply where parameter names match.

Choice per remapped material:
  1. MAP below (hand-picked from the FH2 library, e.g. what FH2's Huracan uses for lights and interior)
  2. same file name in FH2's library (interior_* prefer interiorengine/, others basematerials/)
  3. otherwise keep the converter's remap when its score >= KEEP_SCORE, else keep it and report it
"""
import re
import zipfile
import ziputil

KEEP_SCORE = 0.7

# FH3 material file name -> FH2 library material (relative to _library/materials)
MAP = {
    "gls_ch1norm_alphacutout": "basematerials/gls_clear",
    "grille_012": "basematerials/grilleplastic_012",
    "lights_ch1bump_ch1lmask": "basematerials/lbk_custom_001",
    "lights_smooth_ch1": "basematerials/lbk_smoothchrome",
    "metal_smooth": "interiorengine/aluminum_satin",
    "carpet_006": "interiorengine/carpet_005",
    "leather_embossed_alpha": "interiorengine/blkleather_bump_lgl",
    "leather_textured_custom": "interiorengine/blkleather_textured_001",
    "metal_anodized": "interiorengine/aluminum_anodised_001",
    "metal_anodized_alloptions": "interiorengine/aluminum_anodised_001",
    "metal_brushed_black": "interiorengine/blkplastic_brushed_001",
    "metal_cast": "interiorengine/aluminum_rgh",
    "metal_clearcoat_rough": "interiorengine/aluminum_clearcoat_rough",
    "metal_machined": "interiorengine/aluminum_machined",
    "metal_textured_custom": "interiorengine/aluminum_textured",
    "engine_low": "interiorengine/blkplastic_lgl",
    "plastic": "interiorengine/blkplastic_lgl",
    "plastic_lgl": "interiorengine/blkplastic_lgl",
    "plastic_ngl": "interiorengine/blkplastic_ngl",
    "plastic_sgl": "interiorengine/blkplastic_sgl",
    "plastic_smooth": "interiorengine/plastic_smooth_colored",
    "plastic_textured_001": "interiorengine/blkplastic_textured_001",
    "plastic_textured_custom": "interiorengine/blkplastic_textured_002",
    "seatbelt_press": "interiorengine/blkplastic_mgl",
    "stitch_ch1normal_colorlookup": "interiorengine/stitch_001",
    # FH3 radiosity materials (shader rad_ch2_diffnorm, light-tinted by the car's lamps) are the lamp reflectors and
    # housings themselves; FH2 has no such shader -> plain FH2 equivalents: metal (F0 0.55) -> polished chrome,
    # non-metal (diffuse 0.007) -> black plastic, glass -> clear glass
    "rad_ch2_metal": "basematerials/chrome_polished",
    "rad_ch2_nonmetal": "basematerials/blkplastic_sgl",
    "rad_smoothglass": "basematerials/gls_clear",
}

REMAP_RE = re.compile(r"^- (\S+\.materialbin): REMAPPED:(\S+)->(\S+) \(score ([\d.]+)\)", re.M)


def remaps_from_report(text):
    return [(p, a, b, float(s)) for p, a, b, s in REMAP_RE.findall(text)]


class Library:
    def __init__(self, materials_zip):
        self.z = zipfile.ZipFile(materials_zip)
        self.names = {n.lower(): n for n in self.z.namelist()}
        self.by_base = {}
        for n in self.names:
            self.by_base.setdefault(n.rsplit("/", 1)[-1], []).append(n)

    def pick(self, rel, score):
        folder, base = rel.lower().split("/")[-2:]
        stem = base[:-len(".materialbin")]
        if stem in MAP:
            n = MAP[stem] + ".materialbin"
            return (n, "table") if n in self.names else (None, "table entry %s missing" % n)
        same = self.by_base.get(base, [])
        if same:
            pref = "interiorengine/" if folder.startswith("interior") else "basematerials/"
            same = sorted(same, key=lambda n: (not n.startswith(pref), n))
            return same[0], "same name"
        if score >= KEEP_SCORE:
            return None, "kept converter remap (score %.2f)" % score
        return None, "NO FH2 match, kept converter remap (score %.2f)" % score

    def read(self, n):
        return self.z.read(self.names[n])


def apply(src_zip, dst_zip, remaps, library):
    """Rewrites src_zip into dst_zip with remapped materials replaced; returns log lines."""
    plan, log = {}, []
    for rel, a, b, score in remaps:
        target, why = library.pick(rel, score)
        if target:
            plan[("materials/" + rel).lower()] = library.read(target)
            log.append("%s (%s) -> FH2 %s [%s]" % (rel, a, target, why))
        else:
            log.append("%s (%s -> %s) %s" % (rel, a, b, why))
    done = set()
    with zipfile.ZipFile(src_zip) as zin, ziputil.writer(dst_zip) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            key = info.filename.lower()
            if key in plan:
                data = plan[key]
                done.add(key)
            zout.writestr(info.filename, data)
    for k in set(plan) - done:
        log.append("WARNING: %s not found in the car zip" % k)
    return log
