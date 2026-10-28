# Runs inside IDA. Byte-search `call qword ptr [reg+0A0h]` (FF 9x A0 00 00 00), then look for a read of
# +0x230/+0x234/+0x238 within the next 14 instructions (shadow distance consumers via the settings getter).
import idautils, idc, ida_bytes, ida_funcs, ida_name, ida_segment, ida_ua

found = {}
for s in idautils.Segments():
    seg = ida_segment.getseg(s)
    if not (seg.perm & ida_segment.SEGPERM_EXEC):
        continue
    buf = ida_bytes.get_bytes(seg.start_ea, seg.end_ea - seg.start_ea) or b""
    for modrm in (0x90, 0x91, 0x92, 0x93, 0x95, 0x96, 0x97):
        pat = bytes([0xFF, modrm, 0xA0, 0, 0, 0])
        i = buf.find(pat)
        while i >= 0:
            ea = seg.start_ea + i
            h = ea
            for _ in range(14):
                h = idc.next_head(h, seg.end_ea)
                insn = ida_ua.insn_t()
                if not ida_ua.decode_insn(insn, h):
                    break
                if any(op.type == ida_ua.o_displ and op.addr in (0x230, 0x234, 0x238) for op in insn.ops):
                    f = ida_funcs.get_func(ea)
                    found.setdefault(f.start_ea if f else ea, []).append("%X %s" % (h, idc.generate_disasm_line(h, 0)[:44]))
                    break
            i = buf.find(pat, i + 1)
for fea, lines in sorted(found.items()):
    print("%X %s" % (fea, ida_name.get_name(fea)))
    for l in lines[:3]:
        print("    " + l)
print("total", len(found))
