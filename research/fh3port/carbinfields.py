"""Every field of the carbin CarRenderModel entries for models matching substrings, several cars side by side.
usage: carbinfields.py <model-substring,...> <car.zip> [car.zip ...]"""
import zipfile, struct, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import carbin


def model(r):
    f = []
    v = r.u16(); f.append(("ver", v))
    path = r.s()
    m = r.take(64); f.append(("mat64", struct.unpack("<16f", m)))
    if v < 5:
        f.append(("u32", r.u32()))
    else:
        f.append(("lodmask", hex(r.u16())))
    f.append(("s1", r.s())); f.append(("u16a", r.u16())); f.append(("u8a", r.u8())); f.append(("u32a", hex(r.u32())))
    if v < 9:
        f.append(("s2", r.s()))
    if v >= 2:
        lst = []
        for _ in range(r.count()):
            lst.append((r.s(), r.take(r.count()).hex()))
        f.append(("list2", lst))
    if v >= 3:
        lst = []
        for _ in range(r.count()):
            lst.append((r.s(), r.take(4).hex()))
        f.append(("list3", lst))
    if v >= 6:
        b = r.u8(); f.append(("flag6", b))
        if b:
            f.append(("v6", (hex(r.u32()), hex(r.u32()))))
    if v >= 8:
        f.append(("v8", r.take(4).hex()))
    if v >= 9:
        aos = []
        for _ in range(r.count()):
            av = r.u16(); p = r.s(); a, b = r.u32(), r.u32()
            rest = r.take(16).hex() if av >= 2 else ""
            x = [r.u8()]
            if av >= 3:
                x += [r.u8(), r.u8()]
            aos.append((av, p.split("\\")[-1], hex(a), hex(b), rest, x))
        f.append(("ao", aos))
    if v >= 10:
        f.append(("v10", r.u8()))
    if v >= 11:
        f.append(("v11", (r.u8(), r.u8(), r.take(16).hex())))
    if v >= 12:
        f.append(("v12s", r.s()))
    if v >= 13:
        f.append(("v13", r.take(16).hex()))
    if v >= 14:
        f.append(("v14", (r.take(16).hex(), hex(r.u32()))))
    if v >= 15:
        f.append(("v15", r.take(4).hex()))
    if v >= 16:
        n = r.count(1000); r.take(16 * n)
    r.entries.append((path, f))
    return path


carbin.model = model
keys = sys.argv[1].lower().split(",")
for zp in sys.argv[2:]:
    z = zipfile.ZipFile(zp)
    cb = next(n for n in z.namelist() if n.lower().endswith(".carbin"))
    r = carbin.Reader(z.read(cb)); r.entries = []
    carbin.scene(r)
    print("=====", zp.split("\\")[-1].split("/")[-1])
    for path, f in r.entries:
        name = path.split("\\")[-1].lower()
        if any(k in name for k in keys):
            print(" ", name)
            for k, v in f:
                if k == "mat64":
                    v = tuple(round(x, 3) for x in v)
                print("     %-8s %s" % (k, v))
