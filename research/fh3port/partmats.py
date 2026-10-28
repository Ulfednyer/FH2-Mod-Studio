import zipfile, struct, sys, collections, re
sys.path.insert(0, "."); sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom, meshcheck as mc
zp, car, pat = sys.argv[1], sys.argv[2], sys.argv[3]
z = zipfile.ZipFile(zp)
rep = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port\work\reports\%s\fix_report.md" % car, encoding="utf-8").read()
remapped = {p.lower() for p in re.findall(r"^- (\S+\.materialbin): REMAPPED", rep, re.M)}
use = collections.Counter()
for n in z.namelist():
    p = n.split("/")[-1].lower()
    if not re.search(pat, p): continue
    hs, ents = geom.read_bundle(z.read(n))
    mats = {geom.blob_id(e): next((mc.str7(d, 0)[0] for t, d, *_ in mc.anybundle(e.data) if t == "MATI"), None) for e in ents if e.tag == "MatI"}
    for e in ents:
        if e.tag == "Mesh":
            mp = mats.get(struct.unpack_from("<h", e.data, 0)[0])
            if not mp: continue
            sm = mc.shader_masks(mp, zp, car)
            rel = mp.lower().split("\materials\\")[-1].replace("\\", "/")
            src = "FH2lib" if "_library" in mp.lower() else ("SUBST" if rel in remapped else "FH3-kept")
            use[(p[:22], src, rel, sm[0].split("\\")[-1] if sm else None)] += 1
for k, v in sorted(use.items()): print(v, k)
