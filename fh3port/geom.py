"""
FH3 -> FH2 geometry (modelbin) conversion.

The converter (ForzaToolsCli) leaves FH3 geometry untouched; FH2 then reads FH3's packed vertices with its own
formats (giant tyres, flat body). Everything below was derived from FH2's readers and validated against FH2's own
copy of tire_c (same model in both games):

    POSITION  FH3 RGBA16 SNORM (dxgi 13, code 49): xyz = snorm * scale + offset (per mesh, the 32 bytes Mesh 1.8
              adds), w = normal.x                              -> FH2 RGB32 float (dxgi 6, code 3)
    NORMAL    FH3 RG16 SNORM (dxgi 37, code 52) = normal.yz    -> FH2 RGBA16 float (dxgi 10, code 9) = (x, y, z, 0)
    TANGENT   FH3 RGB10A2 UNORM (dxgi 24, code 48): xyz = normalize(v*2-1), w = +1 if a>=2 else -1
                                                               -> FH2 RGBA16 float (dxgi 10, code 9)
    TEXCOORD, COLOR unchanged.
    Mesh 1.8 -> 1.7: drop the 32-byte scale/offset tail, rewrite binding strides/offsets.
    Modl 1.2 -> 1.1: drop the trailing u16.    Skel 1.0 -> 0.0: drop the trailing u32.

    py geom.py fix <in.zip> <out.zip>
"""
import struct, sys, zipfile
import numpy as np

DXGI_SIZE = {6: 12, 10: 8, 13: 8, 24: 4, 28: 4, 35: 4, 37: 4, 2: 16, 16: 8, 34: 4, 41: 4, 42: 4}
CONVERT = {"POSITION": (13, 49, 6, 3), "NORMAL": (37, 52, 10, 9), "TANGENT": (24, 48, 10, 9)}  # fh3 dxgi, code -> fh2 dxgi, code


class GeomError(Exception):
    pass


# ───────────── bundle access ─────────────

class Entry:
    __slots__ = ("pos", "tag", "ver", "doff", "size", "usize", "meta", "data")


def read_bundle(d):
    if d[:4] != b"burG" or d[4:6] != b"\x01\x00":
        raise GeomError("not a v1.0 bundle")
    count, hsize, total = struct.unpack_from("<HII", d, 6)
    out = []
    for i in range(count):
        e = Entry()
        e.pos = 16 + 24 * i
        e.tag = d[e.pos:e.pos + 4][::-1].decode("latin1")
        e.ver = (d[e.pos + 4], d[e.pos + 5])
        nmeta = struct.unpack_from("<H", d, e.pos + 6)[0]
        moff, e.doff, e.size, e.usize = struct.unpack_from("<IIII", d, e.pos + 8)
        e.meta = {}
        for k in range(nmeta):
            p = moff + 8 * k
            mtag = d[p:p + 4][::-1].decode("latin1")
            szv, rel = struct.unpack_from("<HH", d, p + 4)
            e.meta[mtag] = d[p + rel:p + rel + (szv >> 4)]
        e.data = d[e.doff:e.doff + e.size]
        out.append(e)
    return hsize, out


def write_bundle(d, hsize, entries):
    out = bytearray(d[:hsize])
    pos = (hsize + 3) & ~3
    out += bytes(pos - hsize)
    for e in sorted(entries, key=lambda x: x.doff):
        out[e.pos + 4], out[e.pos + 5] = e.ver
        struct.pack_into("<III", out, e.pos + 12, pos, len(e.data), len(e.data))
        out += e.data
        pos += len(e.data)
        pad = ((pos + 3) & ~3) - pos
        out += bytes(pad)
        pos += pad
    struct.pack_into("<I", out, 12, len(out))
    return bytes(out)


def blob_id(e):
    v = e.meta.get("Id  ")
    return struct.unpack("<i", v[:4])[0] if v and len(v) >= 4 else None


# ───────────── structures ─────────────

def parse_vlay(b):
    p = 0
    nsem = struct.unpack_from("<H", b, p)[0]; p += 2
    sems = []
    for _ in range(nsem):
        n = struct.unpack_from("<I", b, p)[0]; p += 4
        sems.append(b[p:p + n].decode("latin1")); p += n
    nel = struct.unpack_from("<H", b, p)[0]; p += 2
    els = []
    for _ in range(nel):
        sem, idx, slot, fmt, off, inst = struct.unpack_from("<HHIIiI", b, p)
        els.append({"sem": sems[sem], "idx": idx, "slot": slot, "fmt": fmt, "pos": p})
        p += 20
    codes_pos = p
    for i, el in enumerate(els):
        el["code"] = struct.unpack_from("<I", b, p + 4 * i)[0]
        el["code_pos"] = p + 4 * i
    return els


def mark_drops(els):
    """FH2 never has a COLOR channel and only has TEXCOORD4 on glass (with TANGENT4). FH3 adds COLOR0 (mask bit
    0x400) to painted parts; FH2 then picks no valid shader variant and the surface renders black."""
    has_tan4 = any(el["sem"] == "TANGENT" and el["idx"] == 4 for el in els)
    for el in els:
        el["drop"] = el["sem"] == "COLOR" or (el["sem"] == "TEXCOORD" and el["idx"] == 4 and not has_tan4)


def convert_vlay(b, els):
    """Rebuilds the VLay: FH2 formats, dropped elements removed, name list and usage mask recomputed."""
    out = bytearray(b)
    for el in els:
        c = CONVERT.get(el["sem"])
        if c and el["fmt"] == c[0]:
            struct.pack_into("<I", out, el["pos"] + 8, c[2])
            struct.pack_into("<I", out, el["code_pos"], c[3])
    if not any(el.get("drop") for el in els):
        return bytes(out)
    keep = [el for el in els if not el.get("drop")]
    names = []
    for el in keep:
        if el["sem"] not in names:
            names.append(el["sem"])
    res = bytearray(struct.pack("<H", len(names)))
    for n in names:
        res += struct.pack("<I", len(n)) + n.encode("latin1")
    res += struct.pack("<H", len(keep))
    for el in keep:
        rec = bytearray(out[el["pos"]:el["pos"] + 20])
        struct.pack_into("<H", rec, 0, names.index(el["sem"]))
        res += rec
    for el in keep:
        res += out[el["code_pos"]:el["code_pos"] + 4]
    mask = 0
    for el in keep:
        if el["sem"] == "TEXCOORD":
            mask |= 1 << el["idx"]
        elif el["sem"] == "TANGENT":
            mask |= 1 << (5 + el["idx"])
    res += struct.pack("<I", mask)
    return bytes(res)


def parse_mesh(d, ver):
    def ge(mn):
        return ver[0] > 1 or (ver[0] == 1 and ver[1] >= mn)
    p = 0
    def take(fmt):
        nonlocal p
        v = struct.unpack_from(fmt, d, p)
        p += struct.calcsize(fmt)
        return v if len(v) > 1 else v[0]
    m = {}
    take("<hHHBBHB")
    if ge(2): take("<BB")
    if ge(3): take("<B")
    take("<B"); take("<H")
    m["index_buffer"] = take("<i")
    take("<I")
    m["start_index"], m["base_vertex"] = take("<ii")
    m["index_count"], _ = take("<II")
    if ge(6): take("<fI")
    take("<I")
    n = take("<I")
    m["bind_off"] = p
    m["bindings"] = [list(take("<iIII")) for _ in range(n)]
    if ge(4): take("<ii")
    n3 = take("<I")
    p += 4 * n3
    if ge(1): take("<I")
    if ge(5): p += 80
    m["end"] = p
    return m


# ───────────── vertex encoding ─────────────

def decode_tangent(raw):
    v = raw.astype(np.int64)
    xyz = np.stack([((v >> s) & 1023) / 1023.0 * 2 - 1 for s in (0, 10, 20)], 1)
    n = np.linalg.norm(xyz, axis=1, keepdims=True)
    xyz = np.divide(xyz, n, out=np.zeros_like(xyz), where=n > 1e-9)
    w = np.where(((v >> 30) & 3) >= 2, 1.0, -1.0)
    return np.column_stack([xyz, w])


def convert_model(d):
    """Returns converted modelbin bytes, or None when it holds no FH3 geometry."""
    hsize, ents = read_bundle(d)
    meshes = [e for e in ents if e.tag == "Mesh"]
    if not any(e.ver == (1, 8) for e in meshes):
        # no FH3 geometry; still downgrade FH3 model/skeleton headers if present
        if not any((e.tag, e.ver) in (("Modl", (1, 2)), ("Skel", (1, 0))) for e in ents):
            return None
        meshes = []
    vlays = [(e, parse_vlay(e.data)) for e in ents if e.tag == "VLay"]
    for _, els in vlays:
        mark_drops(els)
    verbs = [e for e in ents if e.tag == "VerB"]
    indbs = {blob_id(e): e for e in ents if e.tag == "IndB"}

    # meshes: fields + per-mesh position scale/offset (Mesh 1.8 tail)
    mesh_info = []
    for e in meshes:
        m = parse_mesh(e.data, e.ver)
        tail = e.data[m["end"]:]
        if e.ver == (1, 8):
            if len(tail) != 32:
                raise GeomError("unexpected Mesh 1.8 tail of %d bytes" % len(tail))
            m["scale"] = np.array(struct.unpack_from("<3f", tail, 0))
            m["offset"] = np.array(struct.unpack_from("<3f", tail, 16))
        mesh_info.append((e, m))

    def indices_of(m):
        ib = indbs.get(m["index_buffer"])
        if ib is None:
            return np.zeros(0, np.int64)
        cnt, sz, stride = struct.unpack_from("<IIH", ib.data, 0)
        arr = np.frombuffer(ib.data[16:16 + cnt * stride], dtype="<u4" if stride == 4 else "<u2").astype(np.int64)
        return arr[m["start_index"]:m["start_index"] + m["index_count"]]

    # which layout each vertex buffer really uses: from the meshes (layout index + binding slot). Guessing by element
    # count/stride alone picked the wrong layout when several share those numbers (NSX bumperF_a: 36-byte buffers
    # decoded with 32/40-byte layouts) -> wrong UVs/tangents -> black, untextured, shimmering surfaces.
    vlay_by_id = dict(enumerate(els for e, els in vlays))   # meshes address layouts by position
    used_as = {}
    for e, m in mesh_info:
        lid = struct.unpack_from("<i", e.data, m["bind_off"] - 8)[0]
        for bid, slot, stride, off in m["bindings"]:
            if lid in vlay_by_id:
                used_as.setdefault(bid, set()).add((lid, slot))

    # describe every vertex buffer
    bufs = {}
    for e in verbs:
        cnt, sz, stride, nel, fmt = struct.unpack_from("<IIHHI", e.data, 0)
        info = {"e": e, "count": cnt, "stride": stride, "nel": nel, "fmt": fmt, "els": None}
        uses = used_as.get(blob_id(e), set())
        for lid, slot in sorted(uses):
            se = [el for el in vlay_by_id[lid] if el["slot"] == slot]
            if se and len(se) == nel and sum(DXGI_SIZE.get(el["fmt"], 0) for el in se) == stride:
                if info["els"] is not None and [(x["sem"], x["idx"], x["fmt"]) for x in info["els"]] != \
                        [(x["sem"], x["idx"], x["fmt"]) for x in se]:
                    raise GeomError("buffer %s used with different layouts" % blob_id(e))
                info["els"] = se
        if info["els"] is not None:
            pass
        elif nel == 1 and fmt == 13:
            info["els"] = [{"sem": "POSITION", "fmt": 13}]
        else:
            for _, els in vlays:
                for slot in sorted({el["slot"] for el in els}):
                    se = [el for el in els if el["slot"] == slot]
                    if len(se) == nel and se[0]["fmt"] == fmt and sum(DXGI_SIZE.get(el["fmt"], 0) for el in se) == stride:
                        info["els"] = se
                        break
                if info["els"]:
                    break
        if info["els"] is None:
            raise GeomError("no vertex layout matches buffer id %s (stride %d, %d elements, fmt %d)" % (blob_id(e), stride, nel, fmt))
        bufs[blob_id(e)] = info

    # positions: per-vertex scale/offset from the meshes that draw them; keep w (= normal.x)
    posw = {}
    decoded_pos = {}
    for bid, b in bufs.items():
        if b["els"][0]["sem"] != "POSITION" or b["fmt"] != 13:
            continue
        raw = np.frombuffer(b["e"].data[16:16 + b["count"] * 8], dtype="<i2").reshape(-1, 4).astype(np.float64) / 32767.0
        scale = np.full((b["count"], 3), np.nan)
        offset = np.zeros((b["count"], 3))
        for e, m in mesh_info:
            if "scale" not in m:
                continue
            for bind in m["bindings"]:
                if bind[0] == bid and bind[2]:
                    v = indices_of(m) + m["base_vertex"] + bind[3] // bind[2]
                    v = v[(v >= 0) & (v < b["count"])]
                    scale[v] = m["scale"]
                    offset[v] = m["offset"]
        missing = np.isnan(scale[:, 0])
        if missing.any():
            first = next((m for _, m in mesh_info if "scale" in m), None)
            scale[missing] = first["scale"]
            offset[missing] = first["offset"]
        decoded_pos[bid] = raw[:, :3] * scale + offset
        posw[bid] = raw[:, 3]

    # normal.x for buffers holding NORMAL: from position.w of the vertex drawn together with it
    normal_x = {}
    for e, m in mesh_info:
        pb = next((bd for bd in m["bindings"] if bd[0] in posw and bd[2]), None)
        if pb is None:
            continue
        idx = indices_of(m) + m["base_vertex"]
        pv = idx + pb[3] // pb[2]
        for bd in m["bindings"]:
            if bd is pb or bd[0] not in bufs or not bd[2]:
                continue
            b = bufs[bd[0]]
            if not any(el["sem"] == "NORMAL" for el in b["els"]):
                continue
            sv = idx + bd[3] // bd[2]
            ok = (sv >= 0) & (sv < b["count"]) & (pv >= 0) & (pv < len(posw[pb[0]]))
            arr = normal_x.setdefault(bd[0], np.full(b["count"], np.nan))
            arr[sv[ok]] = posw[pb[0]][pv[ok]]

    # re-encode buffers
    new_stride = {}
    for bid, b in bufs.items():
        n = b["count"]
        rows = np.frombuffer(b["e"].data[16:16 + n * b["stride"]], dtype=np.uint8).reshape(n, b["stride"]) if n else np.zeros((0, b["stride"]), np.uint8)
        cols, off, changed = [], 0, False
        for el in b["els"]:
            size = DXGI_SIZE.get(el["fmt"])
            if size is None:
                raise GeomError("unknown vertex format %d" % el["fmt"])
            raw = rows[:, off:off + size]
            off += size
            if el.get("drop"):
                changed = True
            elif el["sem"] == "POSITION" and el["fmt"] == 13:
                cols.append(decoded_pos[bid].astype("<f4").view(np.uint8).reshape(n, 12)); changed = True
            elif el["sem"] == "NORMAL" and el["fmt"] == 37:
                yz = raw.copy().view("<i2").astype(np.float64).reshape(n, 2) / 32767.0
                x = normal_x.get(bid, np.full(n, np.nan))
                fallback = np.sqrt(np.clip(1 - (yz ** 2).sum(1), 0, 1))
                x = np.where(np.isnan(x), fallback, x)
                cols.append(np.column_stack([x, yz, np.zeros(n)]).astype("<f2").view(np.uint8).reshape(n, 8)); changed = True
            elif el["sem"] == "TANGENT" and el["fmt"] == 24:
                t = decode_tangent(raw.copy().view("<u4").reshape(n))
                cols.append(t.astype("<f2").view(np.uint8).reshape(n, 8)); changed = True
            else:
                cols.append(raw)
        if not changed:
            new_stride[bid] = b["stride"]
            continue
        kept = [el for el in b["els"] if not el.get("drop")]
        if not kept:
            raise GeomError("buffer %s would lose all elements" % bid)
        body = np.hstack(cols) if cols else np.zeros((n, 0), np.uint8)
        stride = body.shape[1]
        first = kept[0]
        first_fmt = CONVERT[first["sem"]][2] if first["sem"] in CONVERT and first["fmt"] == CONVERT[first["sem"]][0] else first["fmt"]
        hdr = bytearray(b["e"].data[:16])
        struct.pack_into("<IIHHI", hdr, 0, n, n * stride, stride, len(kept), first_fmt)
        b["e"].data = bytes(hdr) + body.tobytes() + b["e"].data[16 + n * b["stride"]:]
        new_stride[bid] = stride

    for e, els in vlays:
        e.data = convert_vlay(e.data, els)

    for e, m in mesh_info:
        out = bytearray(e.data[:m["end"]])
        for i, bd in enumerate(m["bindings"]):
            bid, slot, stride, off = bd
            ns = new_stride.get(bid, stride)
            if stride:
                struct.pack_into("<iIII", out, m["bind_off"] + 16 * i, bid, slot, ns, off // stride * ns)
        e.data = bytes(out)
        e.ver = (1, 7)

    for e in ents:
        if e.tag == "Modl" and e.ver == (1, 2):
            e.data, e.ver = e.data[:-2], (1, 1)
        elif e.tag == "Skel" and e.ver == (1, 0):
            e.data, e.ver = e.data[:-4], (0, 0)

    return write_bundle(d, hsize, ents)


def fix_zip(src, dst):
    changed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".modelbin"):
                new = convert_model(data)
                if new is not None:
                    data = new
                    changed += 1
            zout.writestr(info.filename, data)
    return changed


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "fix":
        print("converted %d modelbins" % fix_zip(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
