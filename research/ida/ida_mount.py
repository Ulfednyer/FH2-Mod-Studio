import idc, idautils, ida_bytes, ida_funcs, ida_hexrays, re
out = []
f = 0x140FD1600
for x in idautils.XrefsTo(f):
    out.append("xref to loader: %x %s seg=%s" % (x.frm, idc.get_name(x.frm) or idc.get_func_name(x.frm), idc.get_segm_name(x.frm)))
    if idc.get_segm_name(x.frm) in (".rdata", ".data") or not ida_funcs.get_func(x.frm):
        # walk back to vtable start (previous named location)
        ea = x.frm
        start = ea
        while not idc.get_name(start) and ea - start < 0x800:
            start -= 8
        out.append("   vtable start %x %s, loader slot 0x%x" % (start, idc.get_name(start), x.frm - start))
        mount = ida_bytes.get_qword(start + 0x210)
        out.append("   slot 0x210 -> %x %s" % (mount, idc.get_func_name(mount)))
        try:
            t = str(ida_hexrays.decompile(mount))
            out.append(t[:6000])
        except Exception as e:
            out.append("decompile failed %s" % e)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_mount.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
