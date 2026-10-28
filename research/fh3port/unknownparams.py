"""Per car material: parameters whose hash the resolved FH2 shader doesn't contain (ignored by FH2)."""
import zipfile, struct, sys, os, re, collections
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr, lightparams as lp
from fh3port import FH2_LIB, FH2_SHADERS
src = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\ForzaTechStudio-Main\ForzaTechStudio\Services\NameHashService.cs", encoding="utf-8").read()
known = {int(h, 16): n for h, n in re.findall(r'\{\s*0x([0-9A-Fa-f]{8}),\s*"([^"]+)"\s*\}', src)}
zp, car = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zp)
names = {n.lower(): n for n in z.namelist()}
res = lp.Resolver(names, z.read, car, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS)
filt = sys.argv[3] if len(sys.argv) > 3 else ""
for n in sorted(names):
    if not n.endswith(".materialbin") or filt not in n:
        continue
    d = z.read(names[n])
    sp = res.shader_of_material(d)
    sh = res.shader_bytes(sp) if sp else None
    if not sh:
        print(n, "no shader"); continue
    total, miss = 0, []
    for tag, ver, ep, doff, size in mtpr.blobs(d):
        if tag[::-1] == b"MTPR":
            ps, _ = mtpr.parse_params(d[doff:doff + size], None)
            for s, e, maj, mn, h, typ in ps:
                total += 1
                if struct.pack("<I", h) not in sh:
                    miss.append("%s:%s" % (known.get(h, hex(h)), mtpr.NAMES.get(typ, typ)))
    if miss:
        print("%-55s %-38s %2d/%2d unknown: %s" % (n[:55], sp.split("\\")[-1][:38], len(miss), total, ", ".join(miss[:8])))
