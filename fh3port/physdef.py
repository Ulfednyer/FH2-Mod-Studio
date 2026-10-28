"""physicsdefinition.bin: keep a car's collision shapes inside FH2's 4 KB load arena.

FH2 deserializes a car's PhysicsDefinition into a fixed 0x1000-byte linear arena (crash dump of BMW_M4HE_14:
arena +0x40 = 0x1000). Reader: sub_1412DCC80 ("NumCollisionShapes", "ShapeType", "PointCloudSize", "PointCloud"); when
an allocation does not fit, sub_1412A6670 returns NULL and the reader writes to [NULL+8] -> crash at game+0x12dcda3.
The definition object plus the shape pointer array take 224 + align16(8 * shapes) bytes, every shape blob
align16(size). FH2's own cars top out at 4048 bytes (FIA_595SS_68); several FH3 cars have four 105-point clouds
(~7 KB: M4 HE, Silvia Spec-R HE, Supervan III, Pursuit Ute ...).

File layout (all versions 20..25): u32 1, u32 0, u32 Version, u32 DefinitionType, f32 Mass, 3x3 InertiaTensor,
3x3 InverseInertiaTensor, vec3 HalfExtents, f32 BoundingRadius, vec3 GraphicsOffset, u32 NumChildren,
vec3 AabbCentreOffset (offset 124), u32 NumCollisionShapes (136), then per shape u32 ShapeType + for type 2 (convex
hull) / 5 (point cloud) u32 size + raw blob, then a trailer.
Point cloud blob: u8 type 5, u8 flags, u64 points offset (0x30, self relative) at +8, u32 count at +16, u32 size at
+24, header to 0x30, then count x vec4 points.

Over budget, every point cloud is thinned by farthest-point sampling seeded with the six axis extremes, so the convex
outline the physics uses stays the same shape, only with fewer vertices.

Usage: py physdef.py check <car.zip|physicsdefinition.bin> ...   (OVER = would crash FH2)
       py physdef.py fix <in.zip> <out.zip>
"""
import struct
import sys
import zipfile

ARENA = 0x1000
LIMIT = 4048            # largest need among FH2's own cars (FIA_595SS_68), known to load
BUDGET = 3968           # target when shrinking. FH2's largest stock car needs 4048 with an 8-byte trailer; FH3 trailers are 48 bytes
BASE = 224              # PhysicsDefinition object before the shape pointer array
SHAPES_AT = 136
NAME = "physicsdefinition.bin"
TRAILER = 8             # FH2 trailer: u32 child entries 0, u32 0


def a16(x):
    return (x + 15) & ~15


def parse(d):
    """[(type, offset of size field or None, blob offset, blob size)], end offset. None if not understood."""
    if len(d) < SHAPES_AT + 4:
        return None
    n = struct.unpack_from("<I", d, SHAPES_AT)[0]
    o = SHAPES_AT + 4
    shapes = []
    for _ in range(n):
        if o + 8 > len(d):
            return None
        t = struct.unpack_from("<I", d, o)[0]
        if t not in (2, 5):
            return None     # spheres/boxes are inline records; no car uses them
        size = struct.unpack_from("<I", d, o + 4)[0]
        shapes.append((t, o + 4, o + 8, size))
        o += 8 + size
    return (shapes, o) if o <= len(d) else None


def arena_need(d):
    p = parse(d)
    if p is None:
        return None
    shapes, _ = p
    return BASE + a16(8 * len(shapes)) + sum(a16(s[3]) for s in shapes)


def thin(points, k):
    """Farthest-point sampling: keep k of the points, starting from the axis extremes."""
    if k >= len(points):
        return list(range(len(points)))
    keep = []
    for axis in range(3):
        for pick in (min, max):
            i = pick(range(len(points)), key=lambda j: points[j][axis])
            if i not in keep:
                keep.append(i)
    keep = keep[:k]
    dist = [min(sum((points[j][a] - points[i][a]) ** 2 for a in range(3)) for i in keep) for j in range(len(points))]
    while len(keep) < k:
        j = max(range(len(points)), key=lambda x: dist[x])
        keep.append(j)
        for x in range(len(points)):
            dd = sum((points[j][a] - points[x][a]) ** 2 for a in range(3))
            if dd < dist[x]:
                dist[x] = dd
    return sorted(keep)


def child_count(d):
    """First u32 of the trailer: number of ChildRenderModelIndices entries FH2 reads (0 in all FH2 cars)."""
    p = parse(d)
    if p is None or p[1] + 4 > len(d):
        return 0
    return struct.unpack_from("<I", d, p[1])[0]


def fix(d):
    """Returns (new bytes, log line or None)."""
    lines = []
    d, line = shrink(d)
    if line:
        lines.append(line)
    n = child_count(d)
    if n:
        # FH2 reads n ChildRenderModelIndices entries and indexes its definition list (1 entry) with each:
        # n = 4 (15 FH3 cars: M4 HE, Supervan III, 458 Italia, Hellcat ...) -> NULL definition -> crash game+0x12b04b3.
        # Every FH2 car ends with 8 zero bytes; write that.
        d = d[:parse(d)[1]] + bytes(TRAILER)
        lines.append("child render model table (%d entries) cleared" % n)
    return d, "; ".join(lines) or None


def shrink(d):
    need = arena_need(d)
    if need is None or need <= LIMIT:
        return d, None
    shapes, end = parse(d)
    clouds = [s for s in shapes if s[0] == 5]
    fixed = BASE + a16(8 * len(shapes)) + sum(a16(s[3]) for s in shapes if s[0] != 5) + 48 * len(clouds)
    total = sum(struct.unpack_from("<I", d, s[2] + 16)[0] for s in clouds)
    if not clouds or fixed + 16 * 4 * len(clouds) > BUDGET:
        return d, "needs %d bytes > %d, cannot shrink" % (need, ARENA)
    scale = (BUDGET - fixed) / 16.0 / total
    out = bytearray(d[:SHAPES_AT + 4])
    counts = []
    for t, size_at, blob, size in shapes:
        b = d[blob:blob + size]
        if t == 5:
            off, cnt = struct.unpack_from("<QI", b, 8)
            pts = [struct.unpack_from("<4f", b, off + 16 * i) for i in range(cnt)]
            k = max(4, int(cnt * scale))
            keep = thin(pts, k)
            nb = bytearray(b[:off]) + b"".join(b[off + 16 * i:off + 16 * i + 16] for i in keep)
            struct.pack_into("<I", nb, 16, len(keep))
            struct.pack_into("<I", nb, 24, len(nb))
            b = bytes(nb)
            counts.append("%d->%d" % (cnt, len(keep)))
        out += struct.pack("<II", t, len(b)) + b
    out += d[end:]
    out = bytes(out)
    return out, "collision %d -> %d bytes (FH2 limit %d), point clouds %s" % (
        need, arena_need(out), ARENA, ", ".join(counts))


def fix_zip(src, dst):
    log = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower() == NAME:
                data, line = fix(data)
                if line:
                    log.append(line)
            zout.writestr(info, data)
    return log


def check_zip(path):
    """(need, ok) for a car zip; need None when the file is missing or not understood."""
    with zipfile.ZipFile(path) as z:
        names = {n.lower(): n for n in z.namelist()}
        if NAME not in names:
            return None, True
        d = z.read(names[NAME])
    need = arena_need(d)
    return need, (need is None or need <= LIMIT) and not child_count(d)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        for p in sys.argv[2:]:
            if p.lower().endswith(".zip"):
                need, ok = check_zip(p)
            else:
                d = open(p, "rb").read()
                need = arena_need(d)
                ok = (need is None or need <= LIMIT) and not child_count(d)
            print("%-60s %s %s" % (p, need, "OK" if ok else "OVER (FH2 crashes loading it)"))
    elif len(sys.argv) == 4 and sys.argv[1] == "fix":
        print("\n".join(fix_zip(sys.argv[2], sys.argv[3])) or "nothing to do")
    else:
        print(__doc__)
