import idc, ida_bytes, ida_ua, ida_funcs, ida_segment, struct, ida_hexrays
seg = ida_segment.get_segm_by_name(".text")
out = []
insn = ida_ua.insn_t()
for disp in range(0x5000, 0x50E0, 4):
    pat = struct.pack("<I", disp)
    ea = seg.start_ea
    while True:
        ea = ida_bytes.find_bytes(pat, ea, range_end=seg.end_ea)
        if ea == idc.BADADDR: break
        # try instruction starts a few bytes before
        for back in range(2, 8):
            h = ea - back
            if ida_ua.decode_insn(insn, h) and h + insn.size >= ea + 4 and idc.print_insn_mnem(h) in ("lea", "add"):
                op = insn.ops[1]
                if (op.type == ida_ua.o_displ and op.addr == disp and op.reg not in (4, 5)) or (op.type == ida_ua.o_imm and op.value == disp):
                    f = ida_funcs.get_func(h)
                    out.append("%x %-60s in %s" % (h, idc.GetDisasm(h), idc.get_func_name(f.start_ea) if f else "?"))
                    break
        ea += 1
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_lea.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(out))
