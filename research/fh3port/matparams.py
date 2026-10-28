"""Dump a materialbin's own parameters (names from FTS table). usage: matparams.py <zip> <entry-substring>"""
import zipfile, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
from matidump import params, s7
src = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\ForzaTechStudio-Main\ForzaTechStudio\Services\NameHashService.cs", encoding="utf-8").read()
known = {int(h, 16): n for h, n in re.findall(r'\{\s*0x([0-9A-Fa-f]{8}),\s*"([^"]+)"\s*\}', src)}
z = zipfile.ZipFile(sys.argv[1])
n = next(x for x in z.namelist() if sys.argv[2].lower() in x.lower())
d = z.read(n)
print("==", n)
for tag, ver, ep, doff, size in mtpr.blobs(d):
    b = d[doff:doff + size]
    if tag[::-1] == b"MATL":
        print("  shader", s7(b, 0)[0])
    if tag[::-1] == b"MTPR":
        for h, t, v in params(b):
            print("   %-36s %-9s %s" % (known.get(int(h, 16), h), t, v))
