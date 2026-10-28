import idc, idautils, ida_bytes, ida_funcs, ida_hexrays, re
out = []
funcs = {}
for s in (b"CarPartFrontBumper\0", b"FrontBumper\0", b"RequiresGraphics\0", b"bumperF", b"BumperF", b"_bumper"):
    ea = 0x141E00000
    while True:
        ea = ida_bytes.find_bytes(s, ea, range_end=0x142400000)
        if ea == idc.BADADDR: break
        st = ea
        while ida_bytes.get_byte(st - 1) != 0: st -= 1
        txt = idc.get_strlit_contents(st, -1, 0)
        refs = list(idautils.XrefsTo(st))
        out.append("STR %x %r refs=%s" % (st, txt[:120] if txt else None, ["%x %s" % (r.frm, idc.get_func_name(r.frm)) for r in refs][:6]))
        for r in refs:
            f = ida_funcs.get_func(r.frm)
            if f: funcs.setdefault(f.start_ea, set()).add(txt[:40] if txt else b"?")
        ea += len(s)
for f, names in list(funcs.items())[:6]:
    t = str(ida_hexrays.decompile(f))
    out.append("\n===== %x %s %s len %d =====" % (f, idc.get_func_name(f), names, len(t)))
    for key in ("RequiresGraphics", "Bumper", "bumper"):
        for m in list(re.finditer(key, t))[:3]:
            out.append(t[max(0, m.start() - 700): m.start() + 900])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_bump2.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(funcs))
