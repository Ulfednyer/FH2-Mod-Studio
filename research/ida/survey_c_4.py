import idautils, idc, ida_funcs, ida_name, ida_hexrays, ida_bytes, re, struct
world = re.compile(r'(LOD|Lod|lod|Impostor|Billboard|Cull|Tree|Grass|Crowd|Foliage|Terrain|Stream|FarClip|Draw|MipMap|ShadowCascade|ShadowDist|ShadowEnd|Fog|Horizon|Cubemap|Render|Visib|Pop|Prop|Chunk|Tile|Zone|Sector)')
skip = re.compile(r'(SELECT|IDS_|UI|Skill|Livery|Decal|Menu|Sound|Audio|Mission|Career|Button|Icon|Font|Trigger|Activity|Store|Offer|Photo)')
out = []
for s in idautils.Strings():
    a = int(s.ea)
    t = str(s)
    if a <= 0x141F82A18 or len(t) > 80 or len(t) < 4:
        continue
    if not world.search(t) or skip.search(t):
        continue
    names = []
    for x in idautils.XrefsTo(s.ea):
        f = ida_funcs.get_func(x.frm)
        if f:
            names.append(ida_name.get_name(f.start_ea) or hex(f.start_ea))
    out.append("%X|%s|%s" % (a, t[:60], ",".join(sorted(set(n[:26] for n in names))[:2])))
print("N=%d" % len(out))
print("\n".join(out[:120]))
print("CMD_RENDER: " + " | ".join(
    "%X:%s" % (int(s.ea), str(s)) for s in idautils.Strings()
    if 0x141FF9000 <= int(s.ea) <= 0x141FFB000 and re.search(r'(lod|stream|shadow|render|dist|tree|ambien|far|vis|detail|crowd|grass|draw|cull|shader|fog|sky)', str(s), re.I)))

ea = 0x140396130
f = ida_funcs.get_func(ea)
if f:
    txt = str(ida_hexrays.decompile(f.start_ea)).splitlines()
    kw = re.compile(r'(dist|near|far|lod|scale|clip|fov|"|0\.\d+|\d+\.\d+)', re.I)
    print("## sub_140396130 lines=%d" % len(txt))
    n = 0
    for ln in txt:
        if kw.search(ln):
            print("  " + ln.strip()[:140])
            n += 1
            if n >= 25:
                break
