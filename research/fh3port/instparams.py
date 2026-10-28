"""Material-instance overrides (MatI MTPR) in modelbins: which are unknown to the resolved FH2 shader.
usage: instparams.py <car.zip> <car_name> <modelbin-substring> [material-substring]"""
import zipfile, struct, sys, os, re, collections
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtpr, lightparams as lp
from fh3port import FH2_LIB, FH2_SHADERS
from matidump import params
src = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\ForzaTechStudio-Main\ForzaTechStudio\Services\NameHashService.cs", encoding="utf-8").read()
known = {int(h, 16): n for h, n in re.findall(r'\{\s*0x([0-9A-Fa-f]{8}),\s*"([^"]+)"\s*\}', src)}
zp, car, mk = sys.argv[1], sys.argv[2], sys.argv[3].lower()
mf = sys.argv[4].lower() if len(sys.argv) > 4 else ""
z = zipfile.ZipFile(zp)
names = {n.lower(): n for n in z.namelist()}
res = lp.Resolver(names, z.read, car, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS)
summary = collections.Counter()
for n in sorted(names):
    if not n.endswith(".modelbin") or mk not in n:
        continue
    d = z.read(names[n])
    for tag, ver, ep, doff, size in mtpr.blobs(d):
        if tag[::-1] != b"MatI":
            continue
        inner = d[doff:doff + size]
        mp = None
        for t2, v2, e2, d2, s2 in mtpr.blobs(inner):
            if t2[::-1] == b"MATI":
                mp = lp._s7(inner, d2)[0]
        if not mp or mf not in mp.lower():
            continue
        md = res.material_bytes(mp)
        sp = res.shader_of_material(md) if md else None
        sh = res.shader_bytes(sp) if sp else b""
        for t2, v2, e2, d2, s2 in mtpr.blobs(inner):
            if t2[::-1] == b"MTPR":
                b = inner[d2:d2 + s2]
                ps, _ = mtpr.parse_params(b, None)
                print("--", n.split("/")[-1], mp.split("\\")[-1], "->", (sp or "?").split("\\")[-1])
                for (h, typ, v), p in zip(params(b), ps):
                    hh = int(h, 16)
                    ok = struct.pack("<I", hh) in sh
                    if not ok:
                        summary[(known.get(hh, h), typ)] += 1
                    print("    %s %-34s %-9s %s" % (" " if ok else "X", known.get(hh, h), typ, v))
print("\nunknown to shader (count):")
for k, v in summary.most_common(): print("  ", v, k)
