"""Give every mesh a vertex layout that supplies ALL vertex inputs of its FH2 shader.

Each FH2 shaderbin carries VDCL metadata: one vertex-input mask per render pass (VLay trailer: TEXCOORDi -> bit i,
TANGENTj -> bit 5+j), e.g. m_ch1normglossalphaemissive: 0x2f 0x0 0xf 0x6f 0x1 0x6f 0x6f 0xf (colour passes need 0x6f,
depth/shadow passes 0x0 / 0x1 = alpha UV only), plus a second VDCL entry with the full mask (= union of the passes).
FH2's own cars always supply the full mask (10 cars: 11,597 of 11,597 drawn meshes, 99.3 % exactly). A mesh that only
fits a depth pass is drawn there but not in the colour passes -> black. The first version of this module matched any
single pass mask ("fewest added channels") and picked those depth-pass masks for 221 NSX meshes (lamp housings, lamp
glass, mirrors...); 693 NSX meshes lacked inputs in total (black lamp units, missing lamp covers, dark bumper parts).

Per mesh: target = the union of the shader's VDCL masks, exactly. Supersets must go too: a superset layout (zeroblack
0x4e where FH2 uses 0x4, rotor/undercarriage 0x6f...) made the game build a depth-pass input layout with two
TANGENT0 elements, which Azimuth's D3D12 pipeline creation refused (E_INVALIDARG, "graphics pipeline vs=1011 ps=0").
Every other layout is rebuilt for exactly the target: extra TEXCOORD/TANGENT channels dropped, missing ones
copied from the nearest existing channel of the same kind (TEXCOORD from TEXCOORD, TANGENT from TANGENT; none -> zero
UV / tangent (1,0,0,1)); a copied TEXCOORD also gets the source channel's per-mesh UV transform (copy_uv_transforms).
If all meshes using a layout+buffer want the same target it is changed in place, otherwise
the group gets new VLay/VerB blobs (new Ids). Positions (slot 0) are untouched. Run after geom, matmap and
lightparams (needs final materials).
"""
import struct
import zipfile

import numpy as np

import bundle

SEM_ORDER = {"POSITION": 0, "NORMAL": 1, "TEXCOORD": 2, "TANGENT": 3}
FH2_TEX = (35, 46, 4)      # dxgi R16G16_UNORM, Forza code, bytes
FH2_TAN = (10, 9, 8)       # dxgi R16G16B16A16_FLOAT
SIZE = {6: 12, 10: 8, 35: 4, 2: 16, 16: 8, 34: 4, 41: 4, 42: 4, 13: 8, 24: 4, 28: 4, 37: 4}


def bit_of(sem, idx):
    if sem == "TEXCOORD":
        return 1 << idx
    if sem == "TANGENT":
        return 1 << (5 + idx)
    return 0


# ───────────── VLay ─────────────

def parse_vlay(b):
    p = 0
    nsem = struct.unpack_from("<H", b, p)[0]; p += 2
    names = []
    for _ in range(nsem):
        n = struct.unpack_from("<I", b, p)[0]; p += 4
        names.append(b[p:p + n].decode("latin1")); p += n
    nel = struct.unpack_from("<H", b, p)[0]; p += 2
    els = []
    for i in range(nel):
        si, idx, slot, fmt, off, inst = struct.unpack_from("<HHIIiI", b, p + 20 * i)
        els.append({"sem": names[si], "idx": idx, "slot": slot, "fmt": fmt, "off": off, "inst": inst})
    p += 20 * nel
    for i, el in enumerate(els):
        el["code"] = struct.unpack_from("<I", b, p + 4 * i)[0]
    p += 4 * nel
    mask = struct.unpack_from("<I", b, p)[0]
    return els, mask, b[p + 4:]


def build_vlay(els, tail=b""):
    names = []
    for el in els:
        if el["sem"] not in names:
            names.append(el["sem"])
    out = bytearray(struct.pack("<H", len(names)))
    for n in names:
        out += struct.pack("<I", len(n)) + n.encode("latin1")
    out += struct.pack("<H", len(els))
    for el in els:
        out += struct.pack("<HHIIiI", names.index(el["sem"]), el["idx"], el["slot"], el["fmt"], el["off"], el["inst"])
    for el in els:
        out += struct.pack("<I", el["code"])
    mask = 0
    for el in els:
        mask |= bit_of(el["sem"], el["idx"])
    out += struct.pack("<I", mask)
    return bytes(out) + tail


# ───────────── shader variants ─────────────

def vdcl_masks(d):
    out = set()
    for b in bundle.parse(d) if d[4:6] == b"\x01\x00" else []:
        for mt, mv, md in b.metas:
            if mt[::-1] != b"VDCL":
                continue
            p = 0
            outer = 1
            if mv >= 3:
                outer = struct.unpack_from("<i", md, p)[0]; p += 4
            for _ in range(outer):
                if mv >= 4:
                    p += 2
                n = struct.unpack_from("<i", md, p)[0]; p += 4
                for _ in range(n):
                    h, f = struct.unpack_from("<Ii", md, p); p += 8
                    out.add(f)
    return out


def required(variants):
    """Full vertex-input mask of a shader: union of its per-pass VDCL masks (FH2: equal to the full-mask entry)."""
    full = 0
    for f in variants:
        full |= f
    return full


# ───────────── vertex data ─────────────

def copy_source(sem, idx, have):
    """Channel a missing TEXCOORD/TANGENT is copied from: the nearest existing index of the same kind (ties: lower)."""
    same = sorted((abs(k - idx), k) for k in have)
    return same[0][1] if same else None


def copy_uv_transforms(mesh_data, ver, m, els_old, els_new):
    """Mesh >= 1.5 ends with 5 UV transforms (offset.x, scale.x, offset.y, scale.y; one per TEXCOORD) that turn the
    16-bit UNORM UVs into texture coordinates. A TEXCOORD invented by copying channel k's data must also get channel
    k's transform: FH3 leaves absent channels at identity (0,1,0,1), so a frame mesh whose real UVs (TEXCOORD1) span
    11.6-21.7 got a TEXCOORD0 spanning 0-1 -> its maps sampled a tiny stretched patch (flat, dark surfaces)."""
    if ver < (1, 5):
        return mesh_data
    have = [e["idx"] for e in els_old if e["sem"] == "TEXCOORD"]
    out = bytearray(mesh_data)
    base = m["end"] - 80
    for e in els_new:
        if e["sem"] != "TEXCOORD" or e["idx"] in have or e["idx"] > 4:
            continue
        k = copy_source("TEXCOORD", e["idx"], have)
        if k is not None and k <= 4:
            out[base + 16 * e["idx"]:base + 16 * e["idx"] + 16] = mesh_data[base + 16 * k:base + 16 * k + 16]
    return bytes(out)


def repack(verb, els_old, els_new):
    """verb: VerB blob data (16-byte header + rows + tail). Returns new VerB data for the new slot-1 element list."""
    cnt, nbytes, stride, nel, fmt = struct.unpack_from("<IIHHI", verb, 0)
    rows = np.frombuffer(verb[16:16 + cnt * stride], np.uint8).reshape(cnt, stride) if cnt else np.zeros((0, stride), np.uint8)
    cols, off = {}, 0
    for el in els_old:
        sz = SIZE[el["fmt"]]
        cols[(el["sem"], el["idx"])] = rows[:, off:off + sz]
        off += sz
    if off != stride:
        raise ValueError("element sizes %d != stride %d" % (off, stride))
    parts = []
    for el in els_new:
        key = (el["sem"], el["idx"])
        if key in cols:
            parts.append(cols[key])
            continue
        src = copy_source(el["sem"], el["idx"], [k[1] for k in cols if k[0] == el["sem"]])
        if src is not None:
            parts.append(cols[(el["sem"], src)])
        elif el["sem"] == "TANGENT":
            parts.append(np.tile(np.array([1, 0, 0, 1], "<f2").view(np.uint8), (cnt, 1)))
        else:
            parts.append(np.zeros((cnt, SIZE[el["fmt"]]), np.uint8))
    body = np.hstack(parts) if parts else np.zeros((cnt, 0), np.uint8)
    nstride = body.shape[1]
    hdr = bytearray(verb[:16])
    struct.pack_into("<IIHHI", hdr, 0, cnt, cnt * nstride, nstride, len(els_new), els_new[0]["fmt"])
    return bytes(hdr) + body.tobytes() + verb[16 + cnt * stride:], nstride


def new_layout(els, target):
    """Element list for target mask: POSITION/NORMAL kept, TEXCOORD/TANGENT per target bits."""
    have = {(e["sem"], e["idx"]): e for e in els}
    out = [e for e in els if e["sem"] not in ("TEXCOORD", "TANGENT")]
    slot = next((e["slot"] for e in els if e["sem"] in ("NORMAL", "TEXCOORD", "TANGENT")), 1)
    for i in range(5):
        if target & (1 << i):
            out.append(have.get(("TEXCOORD", i)) or {"sem": "TEXCOORD", "idx": i, "slot": slot, "fmt": FH2_TEX[0],
                                                     "off": -1, "inst": 0, "code": FH2_TEX[1]})
    for j in range(5):
        if target & (1 << (5 + j)):
            out.append(have.get(("TANGENT", j)) or {"sem": "TANGENT", "idx": j, "slot": slot, "fmt": FH2_TAN[0],
                                                    "off": -1, "inst": 0, "code": FH2_TAN[1]})
    return sorted(out, key=lambda e: (e["slot"], SEM_ORDER.get(e["sem"], 9), e["idx"]))


# ───────────── model pass ─────────────

def _id(b):
    m = b.meta(b"  dI")
    return struct.unpack("<i", m[:4])[0] if m and len(m) >= 4 else None


def _with_id(b, new_id, data):
    metas = [(t, v, struct.pack("<i", new_id) + d[4:] if t == b"  dI" else d) for t, v, d in b.metas]
    return bundle.Blob(b.tag, b.ver, metas, data)


def _mesh_layout(data, ver):
    import geom
    m = geom.parse_mesh(data, ver)
    return m, struct.unpack_from("<i", data, m["bind_off"] - 8)[0]


def fix_model(d, variants_of_material):
    """variants_of_material(material path) -> set of VDCL masks or None."""
    import geom
    blobs = bundle.parse(d)
    vlays = dict(enumerate(b for b in blobs if b.tag == b"yaLV"))   # by position (how meshes address them)
    verbs = {_id(b): b for b in blobs if b.tag == b"BreV"}
    mats = {}
    for b in blobs:
        if b.tag == b"ItaM":
            try:
                for ib in bundle.parse(b.data):
                    if ib.tag == b"ITAM":
                        n = 0; s = 0; p = 0
                        while True:
                            c = ib.data[p]; p += 1; n |= (c & 0x7F) << s; s += 7
                            if not c & 0x80:
                                break
                        mats[_id(b)] = ib.data[p:p + n].decode("latin1")
            except ValueError:
                pass
    plans = {}   # (layout id, slot-1 buffer id, target) -> [mesh blob indexes]
    log = []
    for i, b in enumerate(blobs):
        if b.tag != b"hseM":
            continue
        mid = struct.unpack_from("<h", b.data, 0)[0]
        if mid < 0:
            continue
        m, lid = _mesh_layout(b.data, b.ver)
        vb = vlays.get(lid)
        variants = variants_of_material(mats.get(mid)) if mats.get(mid) else None
        if vb is None or not variants:
            continue
        els, mask, _ = parse_vlay(vb.data)
        target = required(variants)
        if not target or mask == target or not any(e["slot"] == 1 for e in els):
            continue
        slot1 = [bd for bd in m["bindings"] if bd[1] == 1 and bd[0] in verbs]
        if len(slot1) != 1:
            continue
        plans.setdefault((lid, slot1[0][0], target), []).append(i)
    if not plans:
        return d, log
    users = {}
    for i, b in enumerate(blobs):
        if b.tag == b"hseM" and struct.unpack_from("<h", b.data, 0)[0] >= 0:
            m, lid = _mesh_layout(b.data, b.ver)
            for bd in m["bindings"]:
                if bd[1] == 1:
                    users.setdefault((lid, bd[0]), set()).add(i)
    # meshes address layouts by POSITION in the VLay sequence (loader sub_1413E9B30 fills an array in blob order; FH2
    # files keep Id == position, the last empty layout has Id -1) -> new layouts are appended and get Id = position.
    # Buffers are looked up by Id (their Ids are not in order) -> new buffers get fresh Ids.
    n_vlays = sum(1 for b in blobs if b.tag == b"yaLV")
    next_bid = max([x for x in verbs if x is not None] + [0]) + 1
    new_blobs = []
    for (lid, bid, target), meshes in sorted(plans.items()):
        vb, verb = vlays[lid], verbs[bid]
        els, mask, tail = parse_vlay(vb.data)
        nels = new_layout(els, target)
        old_slot1 = [e for e in els if e["slot"] == 1]
        new_slot1 = [e for e in nels if e["slot"] == 1]
        vdata, nstride = repack(verb.data, old_slot1, new_slot1)
        ldata = build_vlay(nels, tail)
        in_place = users.get((lid, bid), set()) == set(meshes) and \
            all(k[0] != lid and k[1] != bid for k in users if k != (lid, bid))
        if in_place:
            vb.data, verb.data = ldata, vdata
            new_lid, new_bid = lid, bid
        else:
            new_lid, new_bid = n_vlays, next_bid
            n_vlays += 1
            next_bid += 1
            new_blobs.append(_with_id(vb, new_lid, ldata))
            new_blobs.append(_with_id(verb, new_bid, vdata))
        for i in meshes:
            b = blobs[i]
            m, _ = _mesh_layout(b.data, b.ver)
            md = bytearray(b.data)
            struct.pack_into("<i", md, m["bind_off"] - 8, new_lid)
            for k, (xbid, slot, stride, off) in enumerate(m["bindings"]):
                if slot == 1 and xbid == bid:
                    struct.pack_into("<iIII", md, m["bind_off"] + 16 * k, new_bid, slot, nstride,
                                     (off // stride) * nstride if stride else 0)
            b.data = copy_uv_transforms(bytes(md), b.ver, m, els, nels)
        log.append("layout %d 0x%x -> 0x%x for %d meshes (%s)" % (lid, mask, target, len(meshes), "in place" if in_place else "new layout %d / buffer %d" % (new_lid, new_bid)))
    if new_blobs:
        # FH2 models have at most 10 layouts; appending one per group gave NSX models 17 (old rule: 15, ran) and the
        # game then built a corrupted input layout (two TANGENT0 in R16G16_UNORM, Azimuth: pipeline E_INVALIDARG) -
        # most likely a 16-entry per-model limit. New layouts identical to an existing (final) or earlier new one are
        # dropped and their meshes pointed at that one; positions of the original layouts don't change.
        n0 = len(vlays)
        seen, remap, kept = {}, {}, []
        for pos in range(n0):
            seen.setdefault(vlays[pos].data, pos)
        for k, nb in enumerate(nb for nb in new_blobs if nb.tag == b"yaLV"):
            if nb.data in seen:
                remap[n0 + k] = seen[nb.data]
            else:
                remap[n0 + k] = seen[nb.data] = n0 + len(kept)
                kept.append(_with_id(nb, n0 + len(kept), nb.data))
        for b in blobs:
            if b.tag == b"hseM":
                m, lid = _mesh_layout(b.data, b.ver)
                if lid in remap:
                    md = bytearray(b.data)
                    struct.pack_into("<i", md, m["bind_off"] - 8, remap[lid])
                    b.data = bytes(md)
        new_blobs = kept + [nb for nb in new_blobs if nb.tag != b"yaLV"]
        log.append("new layouts: %d, %d after merging identical ones" % (len(remap), len(kept)))
        # new blobs go right after the last existing VLay / VerB of their kind
        for nb in new_blobs:
            last = max(k for k, b in enumerate(blobs) if b.tag == nb.tag)
            blobs.insert(last + 1, nb)
    log += drop_unused(blobs)
    log += position_only_last(blobs)
    update_modl_counts(blobs)
    return bundle.serialize(blobs), log


def position_only_last(blobs):
    """FH2 invariant (40 cars, 3,423 models, no exception): every layout's Id equals its position, except one
    position-only layout with Id -1, which is always the LAST layout. Layouts appended after it (vlayfix) put it in the
    middle, and the game then built depth/shadow input layouts from the wrong layout (Azimuth: D3D12 pipeline
    E_INVALIDARG with duplicated TEXCOORD/TANGENT entries). Moves Id -1 layouts to the end, renumbers the rest
    Id = position and remaps mesh layout indexes."""
    slots = [k for k, b in enumerate(blobs) if b.tag == b"yaLV"]
    vl = [blobs[k] for k in slots]
    order = [i for i, b in enumerate(vl) if _id(b) != -1] + [i for i, b in enumerate(vl) if _id(b) == -1]
    if order == list(range(len(vl))) and all(_id(b) in (k, -1) for k, b in enumerate(vl)):
        return []
    pos = {old: new for new, old in enumerate(order)}
    for b in blobs:
        if b.tag == b"hseM":
            m, lid = _mesh_layout(b.data, b.ver)
            if lid in pos and pos[lid] != lid:
                md = bytearray(b.data)
                struct.pack_into("<i", md, m["bind_off"] - 8, pos[lid])
                b.data = bytes(md)
    for new, old in enumerate(order):
        b = vl[old]
        blobs[slots[new]] = b if _id(b) in (-1, new) else _with_id(b, new, b.data)
    return ["position-only layout moved to the end (layout order %s)" % order]


def drop_unused(blobs):
    """Remove VerB and VLay blobs no mesh references any more (meshes moved to rebuilt copies). FH2 models never carry
    unused ones; the NSX had up to 8 stale buffers per model. Buffers are addressed by Id (no remap); layouts by
    position -> mesh layout indexes are remapped and layouts whose Id was their position get the new position."""
    used_b, used_l = set(), set()
    for b in blobs:
        if b.tag == b"hseM":
            m, lid = _mesh_layout(b.data, b.ver)
            used_l.add(lid)
            used_b.update(bd[0] for bd in m["bindings"])
    vl = [b for b in blobs if b.tag == b"yaLV"]
    gone_b = [b for b in blobs if b.tag == b"BreV" and _id(b) not in used_b]
    gone_l = [b for k, b in enumerate(vl) if k not in used_l]
    if not gone_b and not gone_l:
        return []
    pos = {}
    for k, b in enumerate(vl):
        if k in used_l:
            pos[k] = len(pos)
    for b in blobs:
        if b.tag == b"hseM":
            m, lid = _mesh_layout(b.data, b.ver)
            if lid in pos and pos[lid] != lid:
                md = bytearray(b.data)
                struct.pack_into("<i", md, m["bind_off"] - 8, pos[lid])
                b.data = bytes(md)
    renamed = {id(b): _with_id(b, pos[k], b.data) for k, b in enumerate(vl) if k in pos and _id(b) == k and pos[k] != k}
    drop = {id(b) for b in gone_b + gone_l}
    blobs[:] = [renamed.get(id(b), b) for b in blobs if id(b) not in drop]
    return ["dropped %d unused buffers, %d unused layouts" % (len(gone_b), len(gone_l))]


def update_modl_counts(blobs):
    """Modl starts with u16 mesh, buffer (VerB+IndB+MBuf+ConB+Skin), layout (VLay) and material (MatI) counts; FH2's loader
    allocates exactly that many buffer slots (sub_1413F1D70 -> sub_1413F2140) - more buffer blobs than declared write
    past the array and crash at game+0xfd841f. All 91 Huracan models follow this rule."""
    modl = next((b for b in blobs if b.tag == b"ldoM"), None)
    if modl is None:
        return
    cnt = lambda *tags: sum(1 for b in blobs if b.tag in tags)
    md = bytearray(modl.data)
    # buffers = every blob Blob_IsModelBuffer (0x1413EEC50) accepts: VerB, IndB, MBuf, ConB and Skin. Counting only the
    # first three made the Alumi Craft's suspension (4 Skin blobs) declare 15 instead of 19 -> crash game+0xfd841f
    struct.pack_into("<HHHH", md, 0, cnt(b"hseM"), cnt(b"BreV", b"BdnI", b"fuBM", b"BnoC", b"nikS"), cnt(b"yaLV"), cnt(b"ItaM"))
    modl.data = bytes(md)


def fix_zip(src, dst, variants_of_material):
    log = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".modelbin"):
                try:
                    data, l = fix_model(data, variants_of_material)
                    log += ["%s: %s" % (info.filename.split("/")[-1], x) for x in l]
                except ValueError as e:
                    log.append("%s: skipped (%s)" % (info.filename.split("/")[-1], e))
            zout.writestr(info.filename, data)
    return log
