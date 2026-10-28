import ida_hexrays, idc, idautils
out = []
for f in (0x1411F49B0,):
    t = str(ida_hexrays.decompile(f))
    out.append("===== %x %s len %d" % (f, idc.get_func_name(f), len(t)))
    out.append(t[:14000])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_mount3.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
