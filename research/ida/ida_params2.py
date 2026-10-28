import idc, idautils, ida_hexrays, ida_bytes, ida_name, re
out = []
def dec(ea, n=5000):
    try:
        t = str(ida_hexrays.decompile(ea))
    except Exception as e:
        t = "fail %s" % e
    out.append("===== %x %s" % (ea, idc.get_func_name(ea)))
    out.append("\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l))[:n])
dec(0x1410AE470, 2500)   # type 6 factory
for name in ("ColorGradientShaderParameter::vftable", "TextureShaderParameter::vftable", "SamplerShaderParameter::vftable"):
    vt = ida_name.get_name_ea(idc.BADADDR, name)
    out.append("vtable %s = %x" % (name, vt))
    if vt != idc.BADADDR:
        dec(ida_bytes.get_qword(vt + 8))
# all *ShaderParameter vtables
names = sorted({n for _, n in idautils.Names() if n.endswith("ShaderParameter::vftable")})
out.append("all param vtables: %s" % names)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_params2.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
