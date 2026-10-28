"""Mesh bucket flags + BucketOrder distribution (FH2 cars vs NSX), split opaque/transparent."""
import zipfile, struct, sys, glob, random, collections
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import bundle
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"


def scan(zp, c):
    z = zipfile.ZipFile(zp)
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not n.lower().startswith("scene/"): continue
        try: bl = bundle.parse(z.read(n))
        except ValueError: continue
        for b in bl:
            if b.tag != b"hseM": continue
            mid, bone, flags, last, first, bucket, order = struct.unpack_from("<hhHBBHB", b.data, 0)
            if mid < 0 or not flags: continue
            kind = "transparent" if bucket & 4 else "decal" if bucket & 2 else "opaque"
            c[(kind, hex(bucket), order)] += 1


fh2 = collections.Counter(); nsx = collections.Counter()
zips = [z for z in glob.glob(M + r"\*_*.zip") if "NSX_16" not in z and "fh3tire" not in z.lower()]
random.seed(5)
for zp in random.sample(zips, 20): scan(zp, fh2)
scan(M + r"\ACU_NSX_16.zip", nsx)
for name, c in (("FH2 (20 cars)", fh2), ("NSX", nsx)):
    print("==", name)
    for kind in ("transparent", "decal", "opaque"):
        items = sorted(((k[1], k[2]), v) for k, v in c.items() if k[0] == kind)
        print("  %-11s" % kind, ", ".join("%s/%d:%d" % (b, o, v) for (b, o), v in items[:40]))
