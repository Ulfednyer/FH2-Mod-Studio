import ida_hexrays, re, idc, idautils, ida_bytes, ida_funcs
t = str(ida_hexrays.decompile(0x141056210))
out = []
for var in ("v356", "v406"):
    for m in re.finditer(r"[^\n]*\b%s\b[^\n]*" % var, t):
        out.append("%s: %s" % (var, m.group().strip()))
# who references the string "CarBodyID"/"CarBodyId" and "List_UpgradeCarBody"
for s in (b"List_UpgradeCarBody", b"CarBodyID\0", b"CarBodyId\0"):
    ea = 0x141E00000
    while True:
        ea = ida_bytes.find_bytes(s, ea, range_end=0x142400000)
        if ea == idc.BADADDR: break
        st = ea
        while ida_bytes.get_byte(st - 1) != 0: st -= 1
        txt = idc.get_strlit_contents(st, -1, 0)
        refs = ["%x %s" % (x.frm, idc.get_func_name(x.frm)) for x in idautils.XrefsTo(st)]
        out.append("STR %x %r refs=%s" % (st, txt[:150] if txt else None, refs[:8]))
        ea += len(s)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_body2.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
