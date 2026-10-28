import idc, ida_funcs, ida_hexrays, idautils
ea = 0x1410C9B47
f = ida_funcs.get_func(ea)
out = ["func %x %s" % (f.start_ea, idc.get_func_name(f.start_ea)),
       "callers: " + ", ".join("%x %s" % (c.frm, idc.get_func_name(c.frm)) for c in idautils.XrefsTo(f.start_ea))]
x = ea
for _ in range(30):
    x = idc.prev_head(x)
y = x
while y < ea + 0x40:
    out.append(("=> " if y == ea else "   ") + "%x  %s" % (y, idc.GetDisasm(y)))
    y = idc.next_head(y)
t = str(ida_hexrays.decompile(f.start_ea))
out.append(t[:12000])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_crash3.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(t))
