import idautils, idc, ida_funcs, ida_ua, ida_hexrays
DISPS = {0x50AC: "stockNorm", 0x50B0: "fitNorm", 0x50B4: "w0", 0x50B8: "w3", 0x50BC: "stockFW", 0x50C0: "stockRW",
         0x50C4: "FrontOff", 0x50C8: "RearOff", 0x50CC: "UpgFront", 0x50D0: "UpgRear", 0x50D9: "aftermarketFlag"}
hits = {}
for seg_start in [0x140E80000]:
    ea = seg_start
    end = 0x141080000
    while ea < end and ea != idc.BADADDR:
        insn = ida_ua.insn_t()
        if ida_ua.decode_insn(insn, ea):
            for op in insn.ops:
                if op.type in (ida_ua.o_displ, ida_ua.o_phrase) and op.addr in DISPS:
                    f = ida_funcs.get_func(ea)
                    if f and f.start_ea != 0x140F697B0:
                        hits.setdefault(f.start_ea, set()).add(DISPS[op.addr])
        ea = idc.next_head(ea, end)
out = []
for f, names in sorted(hits.items()):
    out.append("%x %s: %s" % (f, idc.get_func_name(f), sorted(names)))
for f, names in sorted(hits.items()):
    if {"UpgFront", "aftermarketFlag", "FrontOff"} & names:
        try:
            out.append("\n===== %x =====\n%s" % (f, str(ida_hexrays.decompile(f))[:7000]))
        except Exception as e:
            out.append("decompile fail %x %s" % (f, e))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_users.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(hits))
