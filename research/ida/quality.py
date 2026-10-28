# Runs inside IDA. Default (vf04) + range/options (vf07) of shadow & reflection render controls.
import json, os, re, struct
import idc, ida_name, ida_hexrays, ida_bytes

NAMES = ["ShadowMapResolution", "MaxHiDefShadows", "CollidableShadows", "CrowdDrawShadows", "SkipShadowMapUnlessCockpit",
         "WindshieldReflectionResolution", "EnableWindshieldReflections", "ForceMirrorRender", "HalfRateMirror",
         "MaxCarsInMirror", "CollidablesInMirror", "CrowdDrawMirror", "ParticlesInMirror", "EnvMapFrequencyScale",
         "CarAICubemap", "CarDrawRenderedAO", "CarMinMipBias", "ForceAnisoFiltering", "TonemapAA"]
recs = {r["class"]: r for r in json.load(open(os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json"))) if r["offset"] == 0}


def body(ea):
    return " ".join(l.strip() for l in str(ida_hexrays.decompile(ea)).splitlines()[2:] if l.strip() and "//" not in l)[:220]


for n in NAMES:
    r = recs.get("CDynamicRender%sControl" % n)
    if not r:
        print("%-30s (no class)" % n)
        continue
    base = r["bases"][0] if r["bases"] else ""
    kind = re.sub(r"CDynamicRenderControl|<.*", "", base) or "?"
    d = body(int(r["funcs"][4], 16))
    rng = body(int(r["funcs"][7], 16)) if len(r["funcs"]) > 7 else ""
    # enum option table: off_XXXX referenced in vf07 -> dump (ptr,value) pairs
    opts = ""
    m = re.search(r"&?(off_[0-9A-F]+)", rng)
    cnt = re.search(r"=\s*(\d+);", rng)
    if m and cnt:
        t = ida_name.get_name_ea(idc.BADADDR, m.group(1))
        vals = []
        for i in range(int(cnt.group(1))):
            sp = ida_bytes.get_qword(t + 16 * i)
            s = ida_bytes.get_strlit_contents(sp, -1, 0) or b"?"
            vals.append("%s=%d" % (s.decode(errors="replace"), ida_bytes.get_dword(t + 16 * i + 8)))
        opts = " options: " + ", ".join(vals)
    print("%-30s %-6s default: %s" % (n, kind[:6], d[:90]))
    if rng:
        print("%-30s        range: %s%s" % ("", rng[:120], opts))
