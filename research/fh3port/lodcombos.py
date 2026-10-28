"""Mesh (LODFlags, minLOD, maxLOD) combos and carbin model masks across FH2 cars."""
import zipfile, struct, sys, collections, glob, random
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom
sys.path.insert(0, ".")
from lods import carbin_masks
mesh = collections.Counter(); masks = collections.Counter(); ex = {}
zips = sorted(glob.glob(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\*_*.zip"))
random.seed(1)
for zp in random.sample([z for z in zips if "NSX_16" not in z and "fh3tire" not in z.lower()], 25):
    try:
        z = zipfile.ZipFile(zp)
    except Exception:
        continue
    for n in z.namelist():
        low = n.lower()
        if low.endswith(".carbin"):
            for p, m in carbin_masks(z.read(n)):
                masks[hex(m)] += 1
                ex.setdefault(("mask", hex(m)), p)
        elif low.endswith(".modelbin") and low.startswith("scene/"):
            try:
                hs, ents = geom.read_bundle(z.read(n))
            except Exception:
                continue
            for e in ents:
                if e.tag == "Mesh":
                    f, a, b = struct.unpack_from("<HBB", e.data, 4)
                    mesh[(hex(f), a, b)] += 1
                    ex.setdefault((hex(f), a, b), n.split("/")[-1])
print("mesh combos:")
for k, v in mesh.most_common(40): print("  ", v, k, ex[k])
print("carbin masks:")
for k, v in masks.most_common(): print("  ", v, k, ex[("mask", k)])
