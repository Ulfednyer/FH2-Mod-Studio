import idautils, idc, ida_funcs, ida_name, re
strict = re.compile(r'(Dist|Range|FarClip|NearClip|Fade|LOD|Lod|lod|Impostor|Billboard|Cull|Shadow|Tree|Grass|Crowd|Foliage|Instance|Streaming|MipMap|Bias|VisibleCount|MaxVisible|Draw|Density|Sprite|Terrain|Far|Near)')
skip = re.compile(r'(SELECT|IDS_|UI|Trigger|Activity|Skill|Livery|Decal|Stat|Menu|Sound|Audio|Mission|Career)')
out = []
for s in idautils.Strings():
    a = int(s.ea)
    t = str(s)
    if len(t) > 90 or len(t) < 4:
        continue
    if not strict.search(t) or skip.search(t):
        continue
    names = []
    for x in idautils.XrefsTo(s.ea):
        f = ida_funcs.get_func(x.frm)
        if f:
            names.append(ida_name.get_name(f.start_ea) or hex(f.start_ea))
    names = sorted(set(names))
    out.append("%X|%s|%s" % (a, t[:70], ",".join(n[:28] for n in names[:2])))
print("N=%d" % len(out))
print("\n".join(out[:170]))
