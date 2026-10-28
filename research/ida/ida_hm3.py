import idc, idautils, ida_bytes, ida_hexrays, ida_name, re
out = []
def dec(ea, n=9000):
    try:
        t = str(ida_hexrays.decompile(ea))
    except Exception as e:
        t = "decompile failed %s" % e
    out.append("\n===== %x %s len %d" % (ea, idc.get_func_name(ea), len(t)))
    out.append(t[:n])
    return t
vt = ida_name.get_name_ea(idc.BADADDR, "IOSys::CFileVolume::vftable")
for slot in (216, 224):
    f = ida_bytes.get_qword(vt + slot)
    out.append("CFileVolume slot %d -> %x %s" % (slot, f, idc.get_func_name(f)))
    t = dec(f)
    for sub in sorted(set(re.findall(r"sub_[0-9A-F]{9}", t)))[:12]:
        out.append("   callee " + sub)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_hm3.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
