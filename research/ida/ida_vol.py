import idc, idautils, ida_hexrays, ida_name
out = []
for name in ("IOSys::CFileVolume::vf25", "IOSys::CFileVolume::vf26", "IOSys::CFileVolume::vf2C", "IOSys::CFileVolume::vf1F", "IOSys::CFileVolume::vf23"):
    ea = ida_name.get_name_ea(idc.BADADDR, name)
    t = str(ida_hexrays.decompile(ea))
    callers = sorted({idc.get_func_name(x.frm) or ("data@%x" % x.frm) for x in idautils.XrefsTo(ea)})
    out.append("===== %s %x len %d callers %s" % (name, ea, len(t), callers[:10]))
    out.append(t[:4500])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_vol.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
