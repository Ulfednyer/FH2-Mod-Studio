# Runs inside IDA. 1) context of the single call to the track-settings serializer; 2) CarLODTransDist control methods.
import json, os, re
import idautils, idc, ida_funcs, ida_name, ida_hexrays

call = 0x14134AF97
f = ida_funcs.get_func(call)
lines = str(ida_hexrays.decompile(f.start_ea)).splitlines()
print("== caller %s @%X (%d lines)" % (ida_name.get_name(f.start_ea), f.start_ea, len(lines)))
for i, l in enumerate(lines):
    if "sub_141144320" in l:
        print("\n".join(x.rstrip() for x in lines[max(0, i - 12): i + 3]))
callers = sorted({ida_funcs.get_func(x).start_ea for x in idautils.CodeRefsTo(f.start_ea, 0) if ida_funcs.get_func(x)})
print("its callers:", [ida_name.get_name(c) for c in callers][:6])

recs = json.load(open(os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json")))
for r in recs:
    if r["class"] == "CDynamicRenderCarLODTransDistControl":
        print("== %s vft %s bases %s" % (r["class"], r["vft"], r["bases"]))
        for slot, fs in enumerate(r["funcs"]):
            ea = int(fs, 16)
            body = [l.strip() for l in str(ida_hexrays.decompile(ea)).splitlines() if l.strip() and not l.strip().startswith(("//", "__int64 v", "int v", "float v", "char v", "_QWORD v", "_DWORD v"))]
            print("  slot %d %s: %s" % (slot, ida_name.get_name(ea), " ".join(body[1:12])[:330]))
