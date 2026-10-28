import ida_hexrays, re, idc, idautils, ida_funcs
out = []
def dec(ea, n=6000):
    t = str(ida_hexrays.decompile(ea))
    out.append("===== %x %s" % (ea, idc.get_func_name(ea)))
    out.append("\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l))[:n])
    return t
t = dec(0x1413E99F0, 3000)
# candidate mesh parsers: functions that compare a blob version to 7 or 8 and are near the model loader
cands = set()
for f in idautils.Functions(0x1413E0000, 0x141400000):
    try:
        s = str(ida_hexrays.decompile(f))
    except Exception:
        continue
    if ("1298494312" in s or "0x4D657368" in s or "Mesh" in s) and f not in (0x1413F1D70,):
        cands.add(f)
out.append("mesh-related candidates: " + ", ".join("%x %s" % (c, idc.get_func_name(c)) for c in sorted(cands)))
for c in sorted(cands)[:4]:
    dec(c, 5000)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_meshrd2.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(cands))
