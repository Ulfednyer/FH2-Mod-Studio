import ida_hexrays, re, idc, idautils
t = str(ida_hexrays.decompile(0x1402A4040))
out = ["callers: " + ", ".join("%x %s" % (x.frm, idc.get_func_name(x.frm)) for x in idautils.XrefsTo(0x1402A4040))]
out.append("SQL/strings:")
for m in re.finditer(r'"([^"]{3,})"', t):
    out.append("  " + m.group(1)[:200])
i = t.find('"FrontBumper"')
out.append(t[max(0, i - 3000): i + 3000])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_bump3.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
