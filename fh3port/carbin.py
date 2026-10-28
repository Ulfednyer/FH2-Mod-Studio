"""FH3 -> FH2 .carbin converter.

The parser mirrors FH2's own reader (CarScene::Scene::vf00 0x1411AECB0 and the part/model readers it calls), so a
file parses here exactly when FH2 can read it.  Layout (all little endian, str = u32 length + bytes):

Scene        u16 ver(5) | ver>=3 guid16 | ver>=5 u8 | u32 carId | str name | str skeleton | ver>=2 u16 lodMask
             | ver<4: u32 n + n Part ; else u32 n + n (u8 type, Part)   (type 43 wheel, 4 brake, else plain part)
             | u32 n + n UpgradablePart
Part         u16 ver | u32 id | u32 n + n Model | ver>=2 vec4 x2
UpgradablePart u16 ver | u32 id | u32 n + n Upgrade | ver>=3: u32 n + n (u32 k + k u32 upgradeIds, Model)
Upgrade      u16 ver | u8 | u8 | u32 | u32 | u8 | ver<3: u32 n + n Model | ver>=2 vec4 x2
Model (CarRenderModel11::vf00 0x1411ADEE0, FH2 reads versions up to 0x0F)
             u16 ver | str modelbin | mat4 (64) | ver<5 u32 else u16 lodMask | str parent | u16 | u8 | u32
             | ver<9 str | ver>=2 u32 n + n (str, u32 k + k u8) | ver>=3 u32 n + n (str, f32)
             | ver>=6 u8 droppable [+ u32 dropValue + u32 dropPartId] | ver>=8 f32 breakAmount
             | ver>=9 u32 n + n AOMapInfo | ver>=10 u8 | ver>=11 u8 u8 f32 x4 | ver>=12 str | ver>=13 guid16
             | ver>=14 guid16 u32 | ver>=15 f32
             FH3 ver 0x10 appends: u32 n + n guid16  (dropped on downgrade)
AOMapInfo    u16 ver | str | u32 | u32 | ver==1 u16 u8 / ver>=2 guid16 | u8 | ver>=3 u8 u8

Usage: py carbin.py check <file.carbin|zip>...      parse (FH2 rules + FH3 model v16)
       py carbin.py fix <in.carbin> <out.carbin>    downgrade to FH2
"""
import struct
import sys
import zipfile
import ziputil

FH2_MODEL_MAX = 0x0F


class Fail(Exception):
    pass


class Reader:
    def __init__(self, d):
        self.d, self.p = d, 0
        self.cuts = []      # (start, end) byte ranges to delete
        self.patches = []   # (offset, bytes) to overwrite
        self.stats = {}
        self.lod_masks = []  # (offset of the u16 LOD mask, modelbin path) for model entries v5+
        self.ao_paths = []   # (offset of the AO path string's u32 length, modelbin path, AO path) per AOMapInfo
        self.overrides = []  # (offset of the u32 byte count, modelbin path, instance name) per material override
        self.paint_groups = []  # (offset of the u32 mask, modelbin path, instance name, mask) per paint-group entry

    def take(self, n):
        if self.p + n > len(self.d):
            raise Fail("read past end at 0x%x (+%d)" % (self.p, n))
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u8(self): return self.take(1)[0]
    def u16(self): return struct.unpack("<H", self.take(2))[0]
    def u32(self): return struct.unpack("<I", self.take(4))[0]

    def s(self):
        n = self.u32()
        if n > 4096:
            raise Fail("string length %d at 0x%x" % (n, self.p - 4))
        return self.take(n).decode("latin-1")

    def count(self, limit=100000):
        n = self.u32()
        if n > limit:
            raise Fail("count %d at 0x%x" % (n, self.p - 4))
        return n

    def bump(self, key):
        self.stats[key] = self.stats.get(key, 0) + 1


def ao_map(r):
    v = r.u16()
    r.bump("ao v%d" % v)
    r.ao_paths.append((r.p, getattr(r, "cur_model", ""), r.d[r.p + 4:r.p + 4 + struct.unpack_from("<I", r.d, r.p)[0]].decode("latin-1")))
    r.s(); r.u32(); r.u32()
    if v == 1:
        r.u16(); r.u8()
    elif v >= 2:
        r.take(16)
    r.u8()
    if v >= 3:
        r.u8(); r.u8()


def model(r):
    vpos = r.p
    v = r.u16()
    r.bump("model v%d" % v)
    if v > 0x10:
        raise Fail("model version %d at 0x%x" % (v, vpos))
    path = r.s()
    r.cur_model = path
    r.take(64)
    if v < 5:
        r.u32()
    else:
        r.lod_masks.append((r.p, path))
        r.u16()
    r.s(); r.u16(); r.u8(); r.u32()
    if v < 9:
        r.s()
    if v >= 2:
        # material overrides: (instance name, serialized material bundle). The game builds a material from the bytes
        # (Car_ApplyNamedMaterialOverrides 0x141189830 -> Material_CreateFromBytes) and puts it on every mesh whose
        # material instance has that name; bytes it can't read leave a null material (crash 0x10d72bc)
        for _ in range(r.count()):
            name = r.s()
            n = r.count()
            r.overrides.append((r.p - 4, path, name))
            r.take(n)
    if v >= 3:
        # paint groups: material instance name -> u32 group mask (CarRenderModel11 reader sub_1411B0270; a paint colour
        # with mask M goes onto every instance whose mask overlaps M - Presentation11::CarPresentation::vf53 ->
        # sub_1411B4A60 -> CarRenderModel11::off10_vf27)
        for _ in range(r.count()):
            name = r.s()
            r.paint_groups.append((r.p, path, name, r.u32()))
    if v >= 6:
        if r.u8():
            r.u32(); r.u32()
    if v >= 8:
        r.take(4)
    if v >= 9:
        for _ in range(r.count()):
            ao_map(r)
    if v >= 10:
        r.u8()
    if v >= 11:
        r.u8(); r.u8(); r.take(16)
    if v >= 12:
        r.s()
    if v >= 13:
        r.take(16)
    if v >= 14:
        r.take(16); r.u32()
    if v >= 15:
        r.take(4)
    if v >= 16:
        start = r.p
        n = r.count(1000)
        r.take(16 * n)
        r.cuts.append((start, r.p))
        r.patches.append((vpos, struct.pack("<H", FH2_MODEL_MAX)))
    return path


def part(r):
    v = r.u16()
    r.bump("part v%d" % v)
    r.u32()
    for _ in range(r.count()):
        model(r)
    if v >= 2:
        r.take(32)


def upgrade(r):
    v = r.u16()
    r.bump("upgrade v%d" % v)
    r.u8(); r.u8(); r.u32(); r.u32(); r.u8()
    if v < 3:
        for _ in range(r.count()):
            model(r)
    if v >= 2:
        r.take(32)


def upgradable_part(r):
    v = r.u16()
    r.bump("upart v%d" % v)
    r.u32()
    for _ in range(r.count()):
        upgrade(r)
    if v >= 3:
        for _ in range(r.count()):
            r.take(4 * r.count())
            model(r)


def scene(r):
    v = r.u16()
    r.bump("scene v%d" % v)
    if v >= 3:
        r.take(16)
    if v >= 5:
        r.u8()
    r.car_id_offset = r.p
    r.car_id = r.u32()
    r.media_name = r.s()
    r.skeleton = r.s()
    if v >= 2:
        r.u16()
    n = r.count()
    for _ in range(n):
        if v >= 4:
            r.bump("parttype %d" % r.u8())
        part(r)
    for _ in range(r.count()):
        upgradable_part(r)
    if r.p != len(r.d):
        raise Fail("%d trailing bytes at 0x%x" % (len(r.d) - r.p, r.p))


def parse(d):
    r = Reader(d)
    scene(r)
    return r


def read_metadata(d):
    """Parses .carbin and returns a dict with car_id, media_name, skeleton."""
    r = parse(d)
    return {
        "car_id": getattr(r, "car_id", None),
        "media_name": getattr(r, "media_name", None),
        "skeleton": getattr(r, "skeleton", None),
    }


def downgrade(d, new_car_id=None):
    r = parse(d)
    out = bytearray(d)
    if new_car_id is not None and hasattr(r, "car_id_offset"):
        struct.pack_into("<I", out, r.car_id_offset, new_car_id)
    for off, b in r.patches:
        out[off:off + len(b)] = b
    for start, end in sorted(r.cuts, reverse=True):
        del out[start:end]
    out = bytes(out)
    check = parse(out)
    if check.cuts or any(k.startswith("model v16") for k in check.stats):
        raise Fail("downgrade left FH3 data")
    return out, r


def set_lod_masks(d, paths, old, new):
    """Sets the LOD mask of the model entries whose modelbin path (lowercase) is in paths from old to new."""
    r = parse(d)
    out = bytearray(d)
    n = 0
    for off, path in r.lod_masks:
        if path.lower() in paths and struct.unpack_from("<H", d, off)[0] == old:
            struct.pack_into("<H", out, off, new)
            n += 1
    return bytes(out), n


def set_ao_paths(d, new_paths):
    """new_paths: {offset of an AO path string (from Reader.ao_paths): new path}. Strings are length-prefixed and the
    carbin is read sequentially (no absolute offsets), so they can grow in place."""
    out = bytearray(d)
    for off in sorted(new_paths, reverse=True):
        n = struct.unpack_from("<I", d, off)[0]
        b = new_paths[off].encode("latin-1")
        out[off:off + 4 + n] = struct.pack("<I", len(b)) + b
    return bytes(out)


def _str7(s):
    b = s.encode("latin-1")
    n, out = len(b), bytearray()
    while True:
        c = n & 0x7F
        n >>= 7
        out.append(c | (0x80 if n else 0))
        if not n:
            return bytes(out) + b


def _bundle11_to_blobs(b):
    """FH3 burG 1.1: 20-byte header (count u32 at 16), then the same 24-byte entries and metadata tables as 1.0."""
    import bundle
    count = struct.unpack_from("<I", b, 16)[0]
    blobs = []
    for i in range(count):
        tag, vmaj, vmin, mc, mo, do, size, usize = struct.unpack_from("<4sBBHIIII", b, 20 + 24 * i)
        metas = []
        for k in range(mc):
            mt, sv, rel = struct.unpack_from("<4sHH", b, mo + 8 * k)
            p = mo + 8 * k + rel
            metas.append((mt, sv & 15, b[p:p + (sv >> 4)]))
        blobs.append(bundle.Blob(tag, (vmaj, vmin), metas, b[do:do + size]))
    return blobs


def convert_override(b, car_name, car_names, lib_names):
    """One carbin material override bundle -> FH2: burG 1.1 -> 1.0, MTPR parameters v3 -> v2, and a material path the
    FH2 library lacks pointed at the copy the converter bundled into the car zip (materials/<folder>/<name>)."""
    import bundle
    import mtpr
    blobs = _bundle11_to_blobs(b) if b[4:6] == b"\x01\x01" else bundle.parse(b)
    for bl in blobs:
        if bl.tag == b"ITAM":                      # MATI: str7 material path + rest
            n, s, p = 0, 0, 0
            while True:
                c = bl.data[p]; p += 1; n |= (c & 0x7F) << s; s += 7
                if not c & 0x80:
                    break
            path = bl.data[p:p + n].decode("latin-1")
            rel = path.replace("\\", "/").lower().split("/materials/", 1)[-1]
            if path.lower().startswith("game:\\media\\cars\\_library\\") and rel not in lib_names \
                    and ("materials/" + rel) in car_names:
                path = "Game:\\Media\\cars\\%s\\materials\\%s" % (car_name.lower(), rel.replace("/", "\\"))
            bl.data = _str7(path) + bl.data[p + n:]
    out, _ = mtpr.rebuild_bundle(bundle.serialize(blobs))
    mtpr.strict_check(out)
    return out


def convert_overrides(d, car_name, car_names, lib_names):
    """Rewrites every material override bundle of a carbin for FH2 (length-prefixed, so they may change size)."""
    r = parse(d)
    out = bytearray(d)
    for off, model_path, name in sorted(r.overrides, reverse=True):
        n = struct.unpack_from("<I", d, off)[0]
        if not n:                                  # empty override (Alumi Craft rotor caps): FH2 takes it as it is
            continue
        new = convert_override(d[off + 4:off + 4 + n], car_name, car_names, lib_names)
        out[off:off + 4 + n] = struct.pack("<I", len(new)) + new
    return bytes(out), len(r.overrides)


# Paint-group bits (the same in FH2 and FH3): 0 body, 1 livery, 2 hood, 3 mirrors, 4 wing, 7 windows, 8-11 secondary
# paint, 12-15 second colour of body/hood/mirrors/wing (FH2 paints these with the two-tone colour, black by default).
SECOND_TO_MAIN = {0x1000: 0x1, 0x2000: 0x4, 0x4000: 0x8, 0x8000: 0x10}


def remap_paint_groups(d):
    """A car whose body is only in the second-colour groups (FH3 Centenario: carbon body in 0x1000-0x8000, nothing in
    0x1d) gets painted on its accents in FH2 while the body turns black (two-tone colour unset). FH3 paints those groups
    as the body; move them to the main groups. Returns (new bytes, number of entries changed)."""
    r = parse(d)
    used = 0
    for _, _, _, m in r.paint_groups:
        used |= m
    if used & 0x1d or not used & 0xf000:
        return d, 0
    out = bytearray(d)
    n = 0
    for off, _, _, m in r.paint_groups:
        new = m & ~0xf000
        for hi, lo in SECOND_TO_MAIN.items():
            if m & hi:
                new |= lo
        if new != m:
            struct.pack_into("<I", out, off, new)
            n += 1
    return bytes(out), n


def fix_zip(src, dst, car_name=None, lib_materials=None, new_car_id=None):
    """Copies src to dst with every .carbin downgraded (and, given car_name and the FH2 library Materials.zip path,
    its material overrides converted); returns the number of carbins changed."""
    changed = 0
    lib_names = set()
    if lib_materials:
        with zipfile.ZipFile(lib_materials) as lz:
            lib_names = {n.lower() for n in lz.namelist()}
    with zipfile.ZipFile(src) as zin, ziputil.writer(dst) as zout:
        car_names = {n.lower() for n in zin.namelist()}
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".carbin"):
                n_ovr = 0
                if car_name:
                    data, n_ovr = convert_overrides(data, car_name, car_names, lib_names)
                data, n_pg = remap_paint_groups(data)
                new, r = downgrade(data, new_car_id=new_car_id)
                if r.patches or n_ovr or n_pg or (new_car_id is not None):
                    data = new
                    changed += 1
            zout.writestr(info.filename, data)
    return changed


def _iter_inputs(paths):
    for p in paths:
        if p.lower().endswith(".zip"):
            z = zipfile.ZipFile(p)
            for n in z.namelist():
                if n.lower().endswith(".carbin"):
                    yield p + ":" + n, z.read(n)
        else:
            yield p, open(p, "rb").read()


def main(argv):
    if len(argv) >= 2 and argv[0] == "check":
        bad = 0
        total = {}
        for name, d in _iter_inputs(argv[1:]):
            try:
                r = parse(d)
                for k, c in r.stats.items():
                    total[k] = total.get(k, 0) + c
            except Fail as e:
                bad += 1
                print("FAIL", name, e)
        print("versions:", dict(sorted(total.items())))
        print("failed:", bad)
        return 1 if bad else 0
    if len(argv) == 3 and argv[0] == "fix" and argv[1].lower().endswith(".zip"):
        print("downgraded %d carbins" % fix_zip(argv[1], argv[2]))
        return 0
    if len(argv) == 3 and argv[0] == "fix":
        out, r = downgrade(open(argv[1], "rb").read())
        open(argv[2], "wb").write(out)
        print("models downgraded: %d, bytes removed: %d" % (len(r.patches), sum(e - s for s, e in r.cuts)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
