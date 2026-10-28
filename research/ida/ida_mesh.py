import idc, idautils, ida_funcs, ida_hexrays, ida_ua, ida_segment, re
out = []
TAGS = {"Mesh": 0x4D657368, "Modl": 0x4D6F646C, "Skel": 0x536B656C, "MatI": 0x4D617449}
seg = ida_segment.get_segm_by_name(".text")
hits = {k: set() for k in TAGS}
insn = ida_ua.insn_t()
# scan only functions that also reference the tag constant: use a byte search for the imm32
import ida_bytes, struct
for name, val in TAGS.items():
    pat = struct.pack("<I", val)
    ea = seg.start_ea
    while True:
        ea = ida_bytes.find_bytes(pat, ea, range_end=seg.end_ea)
        if ea == idc.BADADDR:
            break
        f = ida_funcs.get_func(ea)
        if f:
            hits[name].add(f.start_ea)
        ea += 1
for name, fs in hits.items():
    out.append("%s (0x%08X): %d functions: %s" % (name, TAGS[name], len(fs), ["%x %s" % (f, idc.get_func_name(f)) for f in sorted(fs)][:8]))
for name in ("Mesh", "Modl", "Skel"):
    for f in sorted(hits[name])[:3]:
        try:
            t = str(ida_hexrays.decompile(f))
        except Exception as e:
            continue
        checks = re.findall(r"sub_1410F82F0\([^;]*\)", t)
        out.append("\n==== %s handler %x %s len %d version checks: %s" % (name, f, idc.get_func_name(f), len(t), checks[:20]))
        i = t.find(hex(TAGS[name])[2:].upper())
        out.append("\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l))[:3500])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_mesh.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
