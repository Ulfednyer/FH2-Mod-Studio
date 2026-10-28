# Runs inside IDA. 1) every CDynamicRender*Control class + the XML tag its vf02 references;
# 2) aaSampleCount handling in AppCommandLineParameters::vf05.
import json, os, re
import idautils, idc, ida_funcs, ida_name, ida_hexrays

recs = json.load(open(os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json")))
strs = {s.ea: str(s) for s in idautils.Strings()}
rows = []
for r in recs:
    if not re.match(r"CDynamicRender\w*Control$", r["class"]) or r["offset"]:
        continue
    tags = []
    for fs in r["funcs"]:
        f = ida_funcs.get_func(int(fs, 16))
        if not f:
            continue
        for h in idautils.FuncItems(f.start_ea):
            v = idc.get_operand_value(h, 1)
            if v in strs and re.match(r"^[A-Z][A-Za-z0-9]+$", strs[v]) and strs[v] not in tags:
                tags.append(strs[v])
    rows.append((r["class"][len("CDynamicRender"):-len("Control")], tags, r["vft"]))
print("%d control classes:" % len(rows))
for name, tags, vft in sorted(rows):
    print("  %-36s tag=%s" % (name, ",".join(tags[:3])))

print("\n=== aaSampleCount in AppCommandLineParameters::vf05")
lines = str(ida_hexrays.decompile(0x140F6DD60)).splitlines()
for i, l in enumerate(lines):
    if "aaSampleCount" in l:
        print("\n".join(lines[max(0, i - 6): i + 10]))
