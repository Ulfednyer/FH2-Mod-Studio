import ida_hexrays, re
t = str(ida_hexrays.decompile(0x1413F1D70))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_mesh2.txt", "w", encoding="utf-8").write("\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l)))
print("ok")
