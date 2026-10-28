import ida_hexrays, idautils, idc, ida_ua
out = []
f = 0x140F75610
for item in idautils.FuncItems(f):
    d = idc.GetDisasm(item)
    if any(k in d for k in ("50A", "50B", "50C", "50D")):
        out.append("%x  %s" % (item, d))
t = str(ida_hexrays.decompile(f))
out.append("\n" + t[:9000])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_vf09.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(t))
