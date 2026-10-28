import idc, idautils, ida_hexrays, ida_name, ida_bytes
out = []
def dec(ea, n=6000):
    try:
        t = str(ida_hexrays.decompile(ea))
    except Exception as e:
        t = "decompile failed %s" % e
    out.append("\n===== %x %s len %d" % (ea, idc.get_func_name(ea), len(t)))
    out.append(t[:n])
dec(0x14126E0D0)
dec(0x14126D5E0)
dec(0x1411D96A0, 2500)
# who else calls the djb hash (lookups)
out.append("callers of 14126E0D0: " + ", ".join(sorted({"%s" % idc.get_func_name(x.frm) for x in idautils.XrefsTo(0x14126E0D0)})[:30]))
vt = ida_name.get_name_ea(idc.BADADDR, "IOSys::CFileVolume::vftable")
for slot in range(0, 0x260, 8):
    f = ida_bytes.get_qword(vt + slot)
    try:
        t = str(ida_hexrays.decompile(f))
    except Exception:
        continue
    if "14126E0D0" in t or "a1 + 16" in t and "5381" in t:
        out.append("CFileVolume slot 0x%x %s uses the hash" % (slot, idc.get_func_name(f)))
        out.append(t[:3500])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_hm4.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
