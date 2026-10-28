import idc, idautils, ida_bytes, ida_funcs, ida_hexrays
out = []
ea = ida_bytes.find_bytes(b"ERROR: CreateCarBodyPartUpgradeRecord", 0x141E00000)
for x in idautils.XrefsTo(ea):
    f = ida_funcs.get_func(x.frm)
    out.append("xref %x %s" % (x.frm, idc.get_func_name(f.start_ea) if f else "?"))
    if f:
        t = str(ida_hexrays.decompile(f.start_ea))
        out.append(t[:5000])
        out.append("callers: " + ", ".join("%x %s" % (c.frm, idc.get_func_name(c.frm)) for c in idautils.XrefsTo(f.start_ea)))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_bump.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
