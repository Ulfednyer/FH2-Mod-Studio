import idc, idautils, ida_hexrays
out = []
call = 0x140F65E04
ea = call
for _ in range(14):
    ea = idc.prev_head(ea)
lines = []
x = ea
while x <= call + 0x10:
    lines.append("%x  %s" % (x, idc.GetDisasm(x)))
    x = idc.next_head(x)
out.append("\n".join(lines))
t = str(ida_hexrays.decompile(0x140F65E04))
i = t.find("sub_140F697B0")
out.append(t[max(0, i - 2500): i + 800])
# data refs: vtables that hold the loader
for d in (0x1429D5598, 0x14383E1E4):
    out.append("%x name=%s  prev names: %s" % (d, idc.get_name(d), [idc.get_name(d - k * 8) for k in range(1, 12) if idc.get_name(d - k * 8)]))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_call.txt", "w", encoding="utf-8").write("\n\n".join(out))
print("ok")
