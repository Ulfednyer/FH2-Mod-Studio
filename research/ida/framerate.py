# Runs inside IDA. CDynamicRenderFrameRateControl / MotionBlur / MotionBlurSamples controls: vftable + method bodies.
import json, os
import idc, ida_name, ida_hexrays

recs = json.load(open(os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json")))
for cls in ("CDynamicRenderFrameRateControl", "CDynamicRenderMotionBlurControl", "CDynamicRenderMotionBlurSamplesControl"):
    for r in recs:
        if r["class"] != cls or r["offset"]:
            continue
        print("== %s vft %s bases %s" % (cls, r["vft"], r["bases"][:1]))
        for slot in (0, 3, 4, 6, 7, 8):
            if slot >= len(r["funcs"]):
                continue
            ea = int(r["funcs"][slot], 16)
            body = [l.strip() for l in str(ida_hexrays.decompile(ea)).splitlines() if l.strip() and "//" not in l and not l.strip().startswith(("__int64 v", "int v", "char v", "_QWORD v", "_DWORD v", "float v"))]
            print("  vf%02X %-46s %s" % (slot, ida_name.get_name(ea)[:46], " ".join(body[1:14])[:300]))
