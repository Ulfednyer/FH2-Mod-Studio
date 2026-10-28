import sys, zipfile
from collections import Counter
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"
for target in (M + r"\_library\Materials.zip", M + r"\ACU_NSX_16.zip", M + r"\fh3tire_wet_c.zip"):
    tails = Counter()
    for name, data in mtpr.iter_materials(target):
        for tag, ver, _, doff, size in mtpr.blobs(data):
            if tag == b"RPTM":
                blob = data[doff:doff + size]
                _, end = mtpr.parse_params(blob, ver)
                tails[blob[end:].hex(" ")] += 1
    print("==", target.split("\\")[-1], tails.most_common(6))
