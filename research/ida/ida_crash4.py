import idc, ida_funcs, ida_hexrays, idautils, re
out = []
t = str(ida_hexrays.decompile(0x1410C9920))
out.append("== body (no decls)\n" + "\n".join(l for l in t.splitlines() if not re.match(r"\s+\S.*; // ", l))[:5000])
# walk up the call chain and collect string literals to identify the subsystem
seen = set()
frontier = [0x1410C9920]
for depth in range(4):
    nxt = []
    for f in frontier:
        for x in idautils.XrefsTo(f):
            g = ida_funcs.get_func(x.frm)
            if not g or g.start_ea in seen:
                continue
            seen.add(g.start_ea)
            nxt.append(g.start_ea)
            try:
                s = str(ida_hexrays.decompile(g.start_ea))
            except Exception:
                s = ""
            lits = re.findall(r'"([^"]{4,80})"', s)[:12]
            out.append("depth %d: %x %s strings=%s" % (depth + 1, g.start_ea, idc.get_func_name(g.start_ea), lits))
    frontier = nxt
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_crash4.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
