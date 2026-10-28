# Runs inside IDA. Finds instructions using displacement 0x2608 (aaSampleCount) or 0x260C (aaQuality) in code.
import idautils, idc, ida_bytes, ida_funcs, ida_name, ida_segment, ida_ua, ida_hexrays

hits = {}
for seg_ea in idautils.Segments():
    seg = ida_segment.getseg(seg_ea)
    if not (seg.perm & ida_segment.SEGPERM_EXEC):
        continue
    buf = ida_bytes.get_bytes(seg.start_ea, seg.end_ea - seg.start_ea) or b""
    for pat, tag in ((b"\x08\x26\x00\x00", "aaSampleCount"), (b"\x0c\x26\x00\x00", "aaQuality")):
        i = buf.find(pat)
        while i >= 0:
            ea = seg.start_ea + i
            head = idc.get_item_head(ea)
            insn = ida_ua.insn_t()
            if ida_ua.decode_insn(insn, head) and any(op.addr in (0x2608, 0x260C) and op.type in (ida_ua.o_displ, ida_ua.o_phrase) for op in insn.ops):
                hits.setdefault(head, tag)
            i = buf.find(pat, i + 1)
for ea, tag in sorted(hits.items()):
    f = ida_funcs.get_func(ea)
    print("%X %-13s %-38s in %s" % (ea, tag, idc.generate_disasm_line(ea, 0)[:38], ida_name.get_name(f.start_ea) if f else "?"))
