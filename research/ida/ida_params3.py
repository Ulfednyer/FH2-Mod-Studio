import idc, ida_hexrays, ida_bytes, ida_name, re
out = []
def dec(ea, n=4500):
    try:
        t = str(ida_hexrays.decompile(ea))
    except Exception as e:
        t = "fail %s" % e
    out.append("===== %x %s" % (ea, idc.get_func_name(ea)))
    out.append("\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l))[:n])
vt = ida_name.get_name_ea(idc.BADADDR, "Texture2DShaderParameter::vftable")
out.append("Texture2D vtable %x" % vt)
dec(ida_bytes.get_qword(vt + 8))
dec(0x1410F82F0, 1200)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_params3.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
