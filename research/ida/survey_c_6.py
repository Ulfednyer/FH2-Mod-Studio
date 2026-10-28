import idautils, idc, ida_name, re
pat = re.compile(r'(LOD|Lod|lod|Impostor|Billboard|Cull|Visib|GeoChunk|Terrain|Streamer|StreamIn|StreamOut|Tile|Zone|Crowd|Foliage|Tree|Grass|FarClip|DrawDist|MaxDist|Fade)')
hits = []
for ea, nm in idautils.Names():
    if pat.search(nm) and not nm.startswith(("sub_", "unk_", "dword_", "qword_", "off_", "byte_", "word_", "loc_", "stru_", "_")):
        hits.append("%X %s" % (ea, nm[:90]))
print("N=%d" % len(hits))
print("\n".join(hits[:150]))
