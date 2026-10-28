"""Which known parameter names (FTS table) a shader contains, FH2 vs FH3. usage: shnames.py <shader> [filter-regex]"""
import zipfile, struct, sys, re
src = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\ForzaTechStudio-Main\ForzaTechStudio\Services\NameHashService.cs", encoding="utf-8").read()
known = {int(h, 16): n for h, n in re.findall(r'\{\s*0x([0-9A-Fa-f]{8}),\s*"([^"]+)"\s*\}', src)}
sh, flt = sys.argv[1].lower(), re.compile(sys.argv[2] if len(sys.argv) > 2 else ".", re.I)
for label, zp in [("FH2", r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\_library\Shaders.zip"),
                  ("FH3", r"C:\Games\Forza Horizon 3\media\_library\Shaders.zip")]:
    z = zipfile.ZipFile(zp)
    n = next((x for x in z.namelist() if x.lower().endswith("/" + sh + ".shaderbin")), None)
    if not n:
        print(label, "no such shader"); continue
    d = z.read(n)
    names = sorted(v for h, v in known.items() if flt.search(v) and struct.pack("<I", h) in d)
    print(label, sh, ":", ", ".join(names))
