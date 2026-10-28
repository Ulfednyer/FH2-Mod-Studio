import idautils, idc, ida_name, ida_funcs, re, collections
pat = re.compile(r'(LOD|Lod|Impostor|Billboard|Cull|GeoChunk|Terrain|Streamer|Foliage|Crowd|Grass|Tree|Renderable|Streaming|StreamIn|StreamOut|Stream)')
ex = re.compile(r'(Trigger|Bucket|Speed|Race|Mission|Ui|UI|Audio|Sound|Activation|Callable|Func_|Property|Accessor|Constructor|Destructor|MethodImpl|ObjectContainer|SimpleProperty|Achievement|Skill|Replay|Livery|Career|Photo|Event|Store|Offer|Mp|Network|Multiplayer|Socket|Voice|Stat)')
cls = collections.OrderedDict()
for ea, nm in idautils.Names():
    if not pat.search(nm) or ex.search(nm):
        continue
    if nm.startswith(("sub_", "unk_", "dword_", "qword_", "off_", "byte_", "word_", "loc_", "stru_", "_", "j_")):
        continue
    key = nm.split("::")[0][:60]
    cls.setdefault(key, []).append("%X:%s" % (ea, nm[:60]))
print("CLASSES=%d" % len(cls))
for k, v in list(cls.items())[:70]:
    print("%s (%d) e.g. %s" % (k, len(v), v[0][:90]))
