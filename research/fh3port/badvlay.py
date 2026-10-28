"""All VLay blobs in Mount media zips: report TANGENT elements with a non-tangent format or duplicate (sem, idx)."""
import zipfile, glob, collections, sys, os
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle, vlayfix
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
c = collections.Counter(); ex = []
for zp in glob.glob(M + r"\**\*.zip", recursive=True):
    try:
        z = zipfile.ZipFile(zp)
    except Exception:
        continue
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"):
            continue
        try:
            bl = bundle.parse(z.read(n))
        except Exception:
            c["unparsed"] += 1
            continue
        for b in bl:
            if b.tag != b"yaLV":
                continue
            els, mask, _ = vlayfix.parse_vlay(b.data)
            keys = [(e["sem"], e["idx"]) for e in els]
            c["vlay"] += 1
            if len(set(keys)) != len(keys) or any(e["sem"] == "TANGENT" and e["fmt"] != 10 for e in els):
                c["BAD"] += 1
                ex.append((os.path.relpath(zp, M), n, " ".join("%s%d:%d" % (e["sem"][:4], e["idx"], e["fmt"]) for e in els)))
print(dict(c))
for e in ex[:30]:
    print(e)
