"""
Material parameter (MTPR v2.0) reader/writer for FH2 .materialbin bundles.

FH2's reader (sub_1410C9920) accepts parameter types 0-9 and 11; anything else leaves its parameter object null and
the game crashes (game+0x10c9b47). This module parses MTPR blobs, validates them against FH2's payload rules and can
drop parameters FH2 cannot read.

    py mtpr.py check <zip|dir|file>...    report parameter types / unknown types / parse errors
    py mtpr.py fix <in.zip> <out.zip>      rewrite FH3 (v3) parameters as FH2 (v2) in every model/material
"""
import os, struct, sys, zipfile
from collections import Counter

NAMES = {0: "Vector", 1: "Color", 2: "Float", 3: "Bool", 4: "Int", 5: "Swizzle", 6: "Texture2D", 7: "Sampler",
         8: "ColorGradient", 9: "FunctionRange", 11: "Vector2"}
FH2_TYPES = set(NAMES)


class ParseError(Exception):
    pass


def str7(d, p):
    n, shift = 0, 0
    while True:
        if p >= len(d):
            raise ParseError("truncated length")
        b = d[p]; p += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
    return p + n


def param_end(d, p, typ, ver):
    """Returns the offset after a parameter's payload (p points at the payload)."""
    if typ in (0, 1, 5, 9):
        return p + 16
    if typ in (2, 3, 4):
        return p + 4
    if typ == 11:
        return p + 8
    if typ == 6:                       # texture: str7 path + u32 hash
        return str7(d, p) + 4
    if typ == 7:                       # sampler: two u32 in v1.0 (8 bytes); three u32 from v1.1+ (12 bytes)
        return p + (12 if (ver is None or ver >= (1, 1)) else 8)
    if typ == 8:                       # colour gradient: u32 count + count RGBA8
        n = struct.unpack_from("<I", d, p)[0]
        return p + 4 + n * 4
    raise ParseError("unknown parameter type %d" % typ)


def parse_params(d, ver=None):
    """d = MTPR blob data. Returns [(start, end, maj, min, hash, type)]."""
    p = 0
    if ver is not None and ver >= (2, 1):
        if len(d) < 2:
            raise ParseError("truncated parameter count")
        count = struct.unpack_from("<H", d, p)[0]; p += 2
    else:
        if len(d) < 1:
            raise ParseError("truncated parameter count")
        count = d[p]; p += 1
    out = []
    for _ in range(count):
        if p + 6 > len(d):
            raise ParseError("truncated parameter header")
        maj, mn = d[p], d[p + 1]
        h = struct.unpack_from("<I", d, p + 2)[0]
        start = p
        p += 6
        if (maj, mn) >= (3, 1):
            if p >= len(d):
                raise ParseError("truncated parameter header v3.1")
            has_unk = d[p]; p += 1
            if has_unk:
                if p + 4 > len(d):
                    raise ParseError("truncated parameter header v3.1 unk")
                p += 4
        if p >= len(d):
            raise ParseError("truncated parameter type")
        typ = d[p]; p += 1
        if maj >= 3:
            p += 16                    # FH3 parameters (version 3.x) carry a GUID after the type byte
        p = param_end(d, p, typ, (maj, mn))
        if p > len(d):
            raise ParseError("parameter runs past the blob")
        out.append((start, p, maj, mn, h, typ))
    return out, p


def blobs(data):
    """burG bundle v1.0 / v1.1: yields (tag, (maj, min), entry_offset, data_offset, size)."""
    if data[:4] != b"burG":
        raise ParseError("not a bundle")
    maj, mn = data[4], data[5]
    if (maj, mn) == (1, 0):
        count = struct.unpack_from("<H", data, 6)[0]
        p = 16
    else:
        count = struct.unpack_from("<I", data, 16)[0]
        p = 20
    for _ in range(count):
        tag = data[p:p + 4]
        bmaj, bmin = data[p + 4], data[p + 5]
        moff, doff, size = struct.unpack_from("<III", data, p + 8)
        yield tag, (bmaj, bmin), p, doff, size
        p += 24


def check_material(data):
    res = {"types": Counter(), "unknown": Counter(), "errors": []}
    for tag, ver, _, doff, size in blobs(data):
        if tag != b"RPTM":
            continue
        blob = data[doff:doff + size]
        try:
            params, end = parse_params(blob, ver)
            for *_, typ in params:
                res["types"][typ] += 1
            if end != len(blob):
                res["errors"].append("blob v%d.%d: %d trailing bytes" % (ver[0], ver[1], len(blob) - end))
        except ParseError as e:
            msg = str(e)
            if msg.startswith("unknown parameter type"):
                res["unknown"][int(msg.split()[-1])] += 1
            res["errors"].append("v%d.%d: %s" % (ver[0], ver[1], msg))
    return res


def nested_bundles(data):
    """Offsets of every bundle inside a file (modelbins embed material instances as nested bundles)."""
    p = data.find(b"burG")
    while p >= 0:
        yield p
        p = data.find(b"burG", p + 4)


def check_file(data):
    """Checks the MTPR blobs of a file's top bundle and every nested bundle."""
    res = {"types": Counter(), "unknown": Counter(), "errors": []}
    for base in nested_bundles(data):
        try:
            sub = check_material(data[base:])
        except ParseError:
            continue
        res["types"].update(sub["types"]); res["unknown"].update(sub["unknown"])
        res["errors"] += ["@%x %s" % (base, e) for e in sub["errors"] if "trailing" not in e]
    return res


# ───────────── rewriting: FH3 parameters (v3, with GUID) -> FH2 parameters (v2, without) ─────────────

def downgrade_params(blob, ver=(2, 0)):
    """MTPR blob data -> same parameters as v2.0 without GUIDs. Returns (new_blob, changed)."""
    params, end = parse_params(blob, ver)
    if not any(maj >= 3 for _, _, maj, *_ in params):
        return blob, False
    out = bytearray([len(params)])
    for start, stop, maj, mn, h, typ in params:
        if typ not in FH2_TYPES:
            raise ParseError("type %d has no FH2 equivalent" % typ)
        p_hdr = start + 6
        if (maj, mn) >= (3, 1):
            p_hdr += 1 + (4 if blob[p_hdr] else 0)
        p_payload = p_hdr + 1 + (16 if maj >= 3 else 0)
        payload = blob[p_payload:stop]
        if typ == 7 and len(payload) == 8:
            payload = payload + b"\x00\x00\x00\x00"
        out += bytes([2, 0]) + struct.pack("<I", h) + bytes([typ]) + payload
    out += blob[end:]                  # trailer (8-byte hash + 4 bytes, or 16-byte trailer)
    return bytes(out), True


def align4(n):
    return (n + 3) & ~3


def rebuild_bundle(b):
    """Rewrites a v1.0 bundle with downgraded MTPR blobs (recursing into nested material bundles).
    Header bytes (entries + metadata) are kept; blob data is re-laid out 4-byte aligned in the original order."""
    if b[:4] != b"burG" or b[4:6] != b"\x01\x00":
        return b, False
    count, hsize, total = struct.unpack_from("<HII", b, 6)
    entries = []
    for i in range(count):
        e = 16 + 24 * i
        tag = b[e:e + 4]
        bmaj, bmin = b[e + 4], b[e + 5]
        doff, size, usize = struct.unpack_from("<III", b, e + 12)
        entries.append((e, tag, (bmaj, bmin), doff, size, usize))
    changed = False
    new = {}
    for e, tag, bver, doff, size, usize in entries:
        data = b[doff:doff + size]
        if size == usize:                              # uncompressed only
            if tag == b"RPTM":
                data, c = downgrade_params(data, bver)
                changed |= c
            elif data[:4] == b"burG":
                data, c = rebuild_bundle(data)
                changed |= c
        new[e] = data
    if not changed:
        return b, False
    out = bytearray(b[:hsize])
    pos = align4(hsize)
    out += bytes(pos - hsize)
    for e, tag, bver, doff, size, usize in sorted(entries, key=lambda x: x[3]):
        data = new[e]
        struct.pack_into("<III", out, e + 12, pos, len(data), len(data))
        out += data
        pos += len(data)
        pad = align4(pos) - pos
        out += bytes(pad)
        pos += pad
    struct.pack_into("<I", out, 12, len(out))
    return bytes(out), True


def strict_check(data):
    """After rewriting: every MTPR blob must be v2 params of FH2 types ending in the trailer (12 or 16 bytes)."""
    for base in nested_bundles(data):
        try:
            ents = list(blobs(data[base:]))
        except ParseError:
            continue
        for tag, ver, _, doff, size in ents:
            if tag != b"RPTM":
                continue
            blob = data[base + doff:base + doff + size]
            params, end = parse_params(blob, ver)
            bad = [p for p in params if p[2] >= 3 or p[5] not in FH2_TYPES]
            trailer_len = len(blob) - end
            if bad or trailer_len not in (12, 16):
                raise ParseError("@%x: %d bad params, %d trailing bytes" % (base, len(bad), trailer_len))


def fix_zip(src, dst):
    """Copies a zip, rewriting every .modelbin/.materialbin that still holds FH3 parameters. Returns #files changed."""
    changed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith((".modelbin", ".materialbin")):
                new, c = rebuild_bundle(data)
                if c:
                    strict_check(new)
                    data = new
                    changed += 1
            zout.writestr(info.filename, data)
    return changed


EXTS = (".materialbin", ".modelbin")


def iter_materials(target):
    if os.path.isdir(target):
        for root, _, fs in os.walk(target):
            for f in fs:
                if f.lower().endswith(EXTS):
                    p = os.path.join(root, f)
                    yield p, open(p, "rb").read()
    elif target.lower().endswith(".zip"):
        with zipfile.ZipFile(target) as z:
            for n in z.namelist():
                if n.lower().endswith(EXTS):
                    yield target + "!" + n, z.read(n)
    else:
        yield target, open(target, "rb").read()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "fix":
        print("rewrote %d files" % fix_zip(sys.argv[2], sys.argv[3]))
        return
    if len(sys.argv) < 3 or sys.argv[1] != "check":
        print(__doc__); return
    for target in sys.argv[2:]:
        total, types, unknown, bad = 0, Counter(), Counter(), []
        for name, data in iter_materials(target):
            total += 1
            try:
                r = check_file(data)
            except ParseError as e:
                bad.append((name, str(e))); continue
            types.update(r["types"]); unknown.update(r["unknown"])
            if r["errors"]:
                bad.append((name, "; ".join(r["errors"])))
        print("==", target)
        print("   materials %d, parameter types %s" % (total, {NAMES.get(k, k): v for k, v in sorted(types.items())}))
        print("   unknown types %s, materials with problems %d" % (dict(unknown), len(bad)))
        for name, err in bad[:12]:
            print("     ", os.path.basename(name), "->", err)


if __name__ == "__main__":
    main()
