import idautils, idc, idaapi, ida_funcs, ida_name, re, json
pat = re.compile(r'(LOD|Lod|lod|Stream|Impostor|Billboard|Foliage|Tree|Decal|Shadow.?Cascade|FarClip|FarPlane|DrawDist|DrawDistance|MaxDist|VisibleDist|CullDist|ViewDist|MinLOD|MaxLOD|StartFade|LodBias|Visible|ZoneDist|TileDist|Radius)', re.I)
out = []
seen = set()
for s in idautils.Strings():
    t = str(s)
    if not pat.search(t) or len(t) > 120:
        continue
    refs = []
    for x in idautils.XrefsTo(s.ea):
        f = ida_funcs.get_func(x.frm)
        if f:
            n = ida_name.get_name(f.start_ea) or hex(f.start_ea)
            refs.append(n)
    refs = sorted(set(refs))
    if not refs:
        continue
    out.append("%X | %s | %s" % (s.ea, t[:90], ",".join(r[:40] for r in refs[:4])))
print(len(out))
print("\n".join(out[:180]))
