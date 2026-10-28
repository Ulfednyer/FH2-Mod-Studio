import sys, zipfile, struct
from collections import Counter
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"
gaps, aligns, vers, hdr = Counter(), Counter(), Counter(), Counter()
z = zipfile.ZipFile(M + r"\CHE_CorvetteZ06_15.zip")
for n in z.namelist():
    if not n.endswith((".modelbin", ".materialbin")):
        continue
    d = z.read(n)
    for base in mtpr.nested_bundles(d):
        b = d[base:]
        try:
            ents = list(mtpr.blobs(b))
        except Exception:
            continue
        if b[4:6] != b"\x01\x00":
            continue
        count, hsize, total = struct.unpack_from("<HII", b, 6)
        hdr[(hsize % 4, total % 4)] += 1
        prev_end = hsize
        for tag, ver, _, doff, size in sorted(ents, key=lambda e: e[3]):
            gaps[(tag.decode("latin1"), doff - prev_end)] += 1
            aligns[(tag.decode("latin1"), doff % 16)] += 1
            prev_end = doff + size
        gaps[("END", total - prev_end)] += 1
        for tag, ver, *_ in ents:
            vers[(tag.decode("latin1"), ver)] += 1
print("gap before blob (tag, bytes):", sorted(gaps.items(), key=lambda x: -x[1])[:30])
print("offset %16:", sorted(aligns.items(), key=lambda x: -x[1])[:30])
print("blob versions:", dict(vers))
print("header/total %4:", dict(hdr))
