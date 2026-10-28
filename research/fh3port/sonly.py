"""Per model: meshes that are drawn only at LOD S (lodflags == 1) vs all meshes; and SLOD files without sibling."""
import zipfile, struct, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom
for zp in sys.argv[1:]:
    z = zipfile.ZipFile(zp)
    names = [n for n in z.namelist() if n.lower().endswith(".modelbin")]
    low = {n.lower() for n in names}
    print("=====", zp.split("/")[-1])
    for n in names:
        hs, ents = geom.read_bundle(z.read(n))
        flags = [struct.unpack_from("<H", e.data, 4)[0] for e in ents if e.tag == "Mesh"]
        s_only = sum(1 for f in flags if f == 1)
        lod0 = sum(1 for f in flags if f & 2)
        slod = "__slod" in n.lower()
        sibling = n.lower().replace("__slod", "") in low if slod else None
        if s_only and (not slod or not sibling):
            print("  %-45s meshes %3d  S-only %3d  LOD0 %3d  %s" % (n.split("/")[-1], len(flags), s_only, lod0,
                  "SLOD, no sibling" if slod else ""))
