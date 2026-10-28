import ida_hexrays, re, idc
out = []
for ea in (0x1413F2140,):
    t = str(ida_hexrays.decompile(ea))
    out.append("===== %x %s" % (ea, idc.get_func_name(ea)))
    out.append("\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l)))
    for sub in sorted(set(re.findall(r"sub_[0-9A-F]{9}", t)))[:25]:
        out.append("callee " + sub)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_meshrd.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
