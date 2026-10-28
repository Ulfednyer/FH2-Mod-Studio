import idaapi, idautils, idc, ida_bytes, ida_funcs, ida_hexrays

def find_str(s):
    ea = idaapi.inf_get_min_ea()
    pat = ida_bytes.compiled_binpat_vec_t()
    ida_bytes.parse_binpat_str(pat, ea, '"%s"' % s, 16)
    r = ida_bytes.bin_search(ea, idaapi.inf_get_max_ea(), pat, ida_bytes.BIN_SEARCH_FORWARD)
    return r[0] if isinstance(r, tuple) else r

out = []
funcs = set()
for s in ["FROM CarTrackOffsets WHERE", "UpgradeFrontOffset", "NormOffset", "WheelNormOffsets"]:
    ea = find_str(s)
    if ea == idaapi.BADADDR:
        out.append("%s: not found" % s); continue
    # walk back to string start
    start = ea
    while ida_bytes.get_byte(start - 1) not in (0,):
        start -= 1
    out.append("%s @ %x (string start %x)" % (s, ea, start))
    for x in idautils.XrefsTo(start):
        f = ida_funcs.get_func(x.frm)
        out.append("   xref %x in %s" % (x.frm, idc.get_func_name(f.start_ea) if f else "?"))
        if f: funcs.add(f.start_ea)
for f in sorted(funcs):
    out.append("\n===== %s %x =====" % (idc.get_func_name(f), f))
    try:
        out.append(str(ida_hexrays.decompile(f))[:6000])
    except Exception as e:
        out.append("decompile failed: %s" % e)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_offsets.txt", "w", encoding="utf-8").write("\n".join(out))
print("done", len(funcs))
