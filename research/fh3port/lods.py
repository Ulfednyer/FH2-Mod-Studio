"""Carbin model LOD masks and mesh LOD fields for selected parts, NSX vs an FH2 car."""
import zipfile, struct, sys, collections
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import carbin, geom

orig_model = carbin.model


def carbin_masks(d):
    out = []

    def model(r):
        start = r.p
        v = r.u16(); path = r.s(); r.take(64)
        mask = r.u32() if v < 5 else r.u16()
        out.append((path.split("\\")[-1].lower(), mask))
        r.p = start
        return orig_model(r)
    carbin.model = model
    try:
        carbin.parse(d)
    finally:
        carbin.model = orig_model
    return out


def mesh_lods(d):
    hs, ents = geom.read_bundle(d)
    c = collections.Counter()
    for e in ents:
        if e.tag == "Mesh":
            mid, bone, lodflags, lmin, lmax, bucket = struct.unpack_from("<hhHBBH", e.data, 0)
            c[(hex(lodflags), lmin, lmax, hex(bucket))] += 1
    return c


for zp, key in zip(sys.argv[1::2], sys.argv[2::2]):
    z = zipfile.ZipFile(zp)
    cb = z.read(next(n for n in z.namelist() if n.lower().endswith(".carbin")))
    masks = collections.defaultdict(set)
    for p, m in carbin_masks(cb):
        masks[p].add(hex(m))
    print("=====", zp.split("/")[-1])
    for n in z.namelist():
        low = n.lower()
        if low.endswith(".modelbin") and any(k in low for k in key.split(",")):
            print(" ", n.split("/")[-1], "carbin lodmask", sorted(masks.get(low.split("/")[-1], [])))
            for k, v in sorted(mesh_lods(z.read(n)).items()):
                print("      lodflags/min/max/bucket", k, "x", v)
