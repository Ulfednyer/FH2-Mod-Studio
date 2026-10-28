import idc, idautils, ida_bytes, ida_funcs, ida_hexrays
out = []
funcs = set()
ea = 0x141E00000
while True:
    ea = ida_bytes.find_bytes(b"hash.manifest", ea, range_end=0x142400000)
    if ea == idc.BADADDR: break
    st = ea
    while ida_bytes.get_byte(st - 1) not in (0,): st -= 1
    s = idc.get_strlit_contents(st, -1, 0)
    refs = list(idautils.XrefsTo(st)) + list(idautils.XrefsTo(ea))
    out.append("string %x %r refs %s" % (st, s, ["%x %s" % (r.frm, idc.get_func_name(r.frm)) for r in refs]))
    for r in refs:
        f = ida_funcs.get_func(r.frm)
        if f: funcs.add(f.start_ea)
    ea += 13
for f in sorted(funcs):
    t = str(ida_hexrays.decompile(f))
    out.append("\n===== %x %s len %d callers %s" % (f, idc.get_func_name(f), len(t), ["%x %s" % (x.frm, idc.get_func_name(x.frm)) for x in idautils.XrefsTo(f)][:6]))
    out.append(t[:9000])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_hm.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(funcs))
