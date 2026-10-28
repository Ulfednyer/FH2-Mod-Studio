# IDA 9.x / x64 MSVC: RTTI -> named vftables + virtual functions.
# Run 1 scans and caches rtti_classes.json next to the IDB; later runs rename in time-boxed, resumable chunks.
import json, os, re, struct, time
from collections import Counter
import ida_bytes, ida_funcs, ida_name, ida_nalt, ida_segment, ida_xref, idaapi, idautils, idc

BASE = idaapi.get_imagebase()
FLAGS = ida_name.SN_NOWARN | ida_name.SN_NOCHECK | ida_name.SN_FORCE
SHARED_LIMIT = 6  # funcs used by more vftables than this are folded stubs (return 0, nullsub...) - leave alone
CHUNK_SECONDS = 45  # MCP server kills tool calls at 60s
OUT = os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json")
STATE = OUT + ".progress"


def is_exec(seg):
    return bool(seg.perm & ida_segment.SEGPERM_EXEC) or seg.type == ida_segment.SEG_CODE


def is_code(ea):
    seg = ida_segment.getseg(ea)
    return seg is not None and is_exec(seg)


def safe(n):
    return re.sub(r"[^A-Za-z0-9_:]", "_", n)


def class_name(raw):
    d = ida_name.demangle_name("??_7" + raw[4:] + "6B@", 0)
    if d:
        d = d.replace("const ", "", 1)
        return d[: -len("::`vftable'")] if d.endswith("::`vftable'") else d
    return "::".join(reversed(raw[4:-2].split("@")))


def scan():
    data = []
    for s in idautils.Segments():
        seg = ida_segment.getseg(s)
        if not is_exec(seg):
            data.append((seg.start_ea, ida_bytes.get_bytes(seg.start_ea, seg.end_ea - seg.start_ea) or b""))

    # Type descriptors: {pVFTable(type_info), spare, ".?AV...@@\0"}
    cands, vt_count = {}, Counter()
    for start, buf in data:
        for m in re.finditer(rb"\.\?A[VU][\x21-\x7e]+?@@\x00", buf):
            o = m.start() - 0x10
            if o < 0 or (start + o) % 8:
                continue
            vt = struct.unpack_from("<Q", buf, o)[0]
            cands[start + o] = (vt, m.group()[:-1].decode())
            vt_count[vt] += 1
    type_info_vt = vt_count.most_common(1)[0][0]
    td_by_rva = {ea - BASE: raw for ea, (vt, raw) in cands.items() if vt == type_info_vt}

    def td_name(rva):
        raw = td_by_rva.get(rva)
        if raw is None:
            b = ida_bytes.get_strlit_contents(BASE + rva + 0x10, -1, ida_nalt.STRTYPE_C) or b""
            raw = b.decode(errors="replace")
        return class_name(raw) if raw.startswith(".?A") else raw

    # Complete Object Locators: sig=1, offset, cdOffset, TD rva, CHD rva, self rva
    cols = {}
    for start, buf in data:
        for m in re.finditer(rb"(?=\x01\x00\x00\x00)", buf):
            o = m.start()
            if (start + o) % 4 or o + 24 > len(buf):
                continue
            _, off, _, td_rva, chd_rva, self_rva = struct.unpack_from("<IIIIII", buf, o)
            if self_rva == start + o - BASE and td_rva in td_by_rva:
                cols[start + o] = (off, td_rva, chd_rva)

    # vftable = (qword pointing at a COL) + 8
    vft_cols = []
    for start, buf in data:
        pad = (-start) % 8
        body = buf[pad: pad + (len(buf) - pad) // 8 * 8]
        for i, (q,) in enumerate(struct.iter_unpack("<Q", body)):
            if q in cols:
                vft_cols.append((start + pad + i * 8 + 8, q))

    def bases(chd_rva):
        chd = BASE + chd_rva
        n, arr = ida_bytes.get_dword(chd + 8), BASE + ida_bytes.get_dword(chd + 12)
        return [td_name(ida_bytes.get_dword(BASE + ida_bytes.get_dword(arr + 4 * i))) for i in range(min(n, 256))]

    def entries(vft):
        out, ea = [], vft
        while len(out) < 4096:
            if ea != vft and ida_xref.get_first_dref_to(ea) != idaapi.BADADDR:
                break
            q = ida_bytes.get_qword(ea)
            if not is_code(q):
                break
            out.append(q)
            ea += 8
        return out

    records = []
    for vft, col in vft_cols:
        off, td_rva, chd_rva = cols[col]
        records.append({"class": td_name(td_rva), "vft": hex(vft), "offset": off,
                        "bases": bases(chd_rva)[1:], "funcs": [hex(f) for f in entries(vft)]})
    # base classes first so inherited-but-not-overridden slots keep the base's name
    records.sort(key=lambda r: (len(r["bases"]), r["offset"], int(r["vft"], 16)))
    with open(OUT, "w") as fh:
        json.dump(records, fh, indent=1)
    print("[rtti] TDs=%d COLs=%d vftables=%d -> %s" % (len(td_by_rva), len(cols), len(records), OUT))


def rename():
    records = json.load(open(OUT))
    usage = Counter(f for r in records for f in set(r["funcs"]))
    start = int(open(STATE).read()) if os.path.exists(STATE) else 0
    t0, named_vft, named_fn, idx = time.time(), 0, 0, start
    while idx < len(records) and time.time() - t0 < CHUNK_SECONDS:
        r = records[idx]
        idx += 1
        cls = safe(r["class"])
        sub = "" if r["offset"] == 0 else "off%X_" % r["offset"]
        vft = int(r["vft"], 16)
        if ida_bytes.has_dummy_name(ida_bytes.get_flags(vft)):
            ida_name.set_name(vft, "%s::%svftable" % (cls, sub), FLAGS)
            named_vft += 1
        if r["bases"] and not idc.get_cmt(vft, 1):
            idc.set_cmt(vft, "bases: " + ", ".join(r["bases"]), 1)
        for i, fs in enumerate(r["funcs"]):
            if usage[fs] > SHARED_LIMIT:
                continue
            f = int(fs, 16)
            if not ida_funcs.get_func(f):
                ida_funcs.add_func(f)
            if ida_bytes.has_dummy_name(ida_bytes.get_flags(f)):
                ida_name.set_name(f, "%s::%svf%02X" % (cls, sub, i), FLAGS)
                named_fn += 1
    open(STATE, "w").write(str(idx))
    print("[rtti] records %d..%d of %d: +%d vftables, +%d funcs%s" % (
        start, idx, len(records), named_vft, named_fn, " DONE" if idx >= len(records) else ""))


if os.path.exists(OUT):
    rename()
else:
    scan()
