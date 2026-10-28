import ida_hexrays, idc, idautils
out = []
t = str(ida_hexrays.decompile(0x140EB7B50))
i = t.find("SELECT FrontTireWidth,FrontWheelDiameter")
out.append("len %d" % len(t))
out.append(t[max(0, i - 1500): i + 3500])
out.append("callers: " + ", ".join("%x %s" % (x.frm, idc.get_func_name(x.frm)) for x in idautils.XrefsTo(0x140EB7B50)))
t2 = str(ida_hexrays.decompile(0x1410495A0))
out.append("\n===== 1410495A0 =====\n" + t2[:3500])
out.append("callers: " + ", ".join("%x %s" % (x.frm, idc.get_func_name(x.frm)) for x in idautils.XrefsTo(0x1410495A0)))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_tw.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
