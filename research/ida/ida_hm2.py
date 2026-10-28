import idc, idautils, ida_bytes, ida_hexrays, ida_name, re
out = []
def dec(ea, n=7000):
    try:
        t = str(ida_hexrays.decompile(ea))
    except Exception as e:
        t = "decompile failed %s" % e
    out.append("\n===== %x %s len %d" % (ea, idc.get_func_name(ea), len(t)))
    out.append(t[:n])
    return t
vt = ida_name.get_name_ea(idc.BADADDR, "IOSys::CMultiVolume::vftable")
mount = ida_bytes.get_qword(vt + 488)
out.append("CMultiVolume vftable %x slot488 -> %x %s" % (vt, mount, idc.get_func_name(mount)))
t = dec(mount, 9000)
# callees of the mount function that look like loaders
callees = sorted({idc.get_func_name(x) for x in re.findall(r"sub_[0-9A-F]+", t) and []})
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_hm2.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
