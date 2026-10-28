# Runs inside IDA. 1) all setting-name strings referenced by the DynamicRenderSettings parser;
# 2) MSAA / draw-distance related strings with referencing functions.
import re
import idautils, idc, ida_funcs, ida_name

strs = {s.ea: str(s) for s in idautils.Strings()}
by_text = {}
for ea, t in strs.items():
    by_text.setdefault(t, []).append(ea)


def funcs_of(ea, limit=4):
    out = set()
    for x in idautils.XrefsTo(ea):
        f = ida_funcs.get_func(x.frm)
        out.add("%s@%X" % (ida_name.get_name(f.start_ea), f.start_ea) if f else "data@%X" % x.frm)
    return sorted(out)[:limit]


# 1. parser: function(s) referencing "CarLODTransDist"
parsers = set()
for ea in by_text.get("CarLODTransDist", []):
    for x in idautils.XrefsTo(ea):
        f = ida_funcs.get_func(x.frm)
        parsers.add(f.start_ea if f else x.frm)
print("CarLODTransDist referenced from:", ["%X" % p for p in parsers])
for p in parsers:
    f = ida_funcs.get_func(p)
    names = []
    if f:
        for h in idautils.FuncItems(f.start_ea):
            for i in range(2):
                v = idc.get_operand_value(h, i)
                if v in strs and re.match(r"^[A-Za-z][A-Za-z0-9_]{2,}$", strs[v]):
                    names.append(strs[v])
    else:  # data table: walk qwords around the reference
        for o in range(-0x400, 0x400, 8):
            v = idc.get_qword(p + o)
            if v in strs:
                names.append(strs[v])
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    print("%d names in %X:" % (len(seen), p))
    print(" ".join(seen))

# 2. MSAA / distance strings
PAT = re.compile(r"msaa|multisampl|samplecount|antialias|\bAA\b|DrawDist|ViewDist|FarClip|FarPlane|ClipDist|LodDist|LODDist|LodScale|LODScale|LodBias|CullDist|FadeDist|DistScale|StreamingDist|DrawRange|MaxDist", re.I)
print("\n--- msaa/distance strings")
n = 0
for ea, t in sorted(strs.items()):
    if PAT.search(t) and len(t) < 90:
        print("%X %-60r %s" % (ea, t, funcs_of(ea)))
        n += 1
        if n > 140:
            break
