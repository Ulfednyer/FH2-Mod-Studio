import idc, ida_bytes, ida_hexrays, idautils, re
out = []
call = 0x140F64C4E
ea = call
for _ in range(12):
    ea = idc.prev_head(ea)
while ea <= call:
    out.append("%x  %s" % (ea, idc.GetDisasm(ea)))
    ea = idc.next_head(ea)
# find who constructs the object passed: look for lea of a vftable into the object nearby in App::Initialize
t = str(ida_hexrays.decompile(idc.get_func_attr(call, idc.FUNCATTR_START)))
i = t.find("sub_140FD1600")
out.append(t[max(0, i - 2500): i + 300])
# candidate classes: vtables named IOSys/FileSystem/Device whose slot 0x210 is a function
for ea2, name in idautils.Names():
    if "vftable" in name and re.search(r"IOSys|FileSystem|FileDevice|ZipFile|Archive|CFileRes", name):
        tgt = ida_bytes.get_qword(ea2 + 0x210)
        fn = idc.get_func_name(tgt)
        if fn:
            out.append("VT %s slot0x210 -> %s %x" % (name[:120], fn[:80], tgt))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_mount2.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
