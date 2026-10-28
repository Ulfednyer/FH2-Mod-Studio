import sys, zipfile, struct
from collections import Counter
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
z = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\ACU_NSX_16.zip")
same = diff = 0
examples = []
posbufs = Counter()
for n in z.namelist():
    if not n.endswith(".modelbin"):
        continue
    d = z.read(n)
    tails, nverb, nvlay = set(), 0, 0
    try:
        ents = list(mtpr.blobs(d))
    except Exception:
        continue
    for tag, ver, e, doff, size in ents:
        if tag == b"hseM":
            tails.add(d[doff + size - 32:doff + size])
        nverb += tag == b"BreV"
        nvlay += tag == b"yaLV"
    if len(tails) <= 1:
        same += 1
    else:
        diff += 1
        if len(examples) < 4:
            examples.append((n, len(tails), [struct.unpack("<8f", t) for t in list(tails)[:3]]))
    posbufs[(nverb, nvlay)] += 1
print("models with one scale/offset for all meshes: %d, with several: %d" % (same, diff))
for e in examples:
    print(e[0], e[1], [tuple(round(x, 4) for x in t) for t in e[2]])
print("(VerB count, VLay count) per model:", posbufs.most_common(10))
