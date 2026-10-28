import idautils, idc, ida_funcs, ida_ua, json
out = []
for tgt in (0x140F697B0, 0x140F514A0):
    out.append("callers of %x %s:" % (tgt, idc.get_func_name(tgt)))
    for x in idautils.XrefsTo(tgt):
        f = ida_funcs.get_func(x.frm)
        out.append("   %x in %s (type %d)" % (x.frm, idc.get_func_name(f.start_ea) if f else "data:" + (idc.get_name(x.frm) or "?"), x.type))
# lea reg, [base+0x5000..0x5100] anywhere -> may be a pointer to the wheel-offset block
insn = ida_ua.insn_t()
hits = {}
for fea in idautils.Functions(0x140E00000, 0x141200000):
    for item in idautils.FuncItems(fea):
        if ida_ua.decode_insn(insn, item) <= 0: continue
        if insn.itype in (ida_ua.get_itype if False else (), ) : pass
        mn = idc.print_insn_mnem(item)
        if mn == "lea" and insn.ops[1].type == ida_ua.o_displ and 0x5080 <= insn.ops[1].addr <= 0x50E0:
            hits.setdefault("%x %s" % (fea, idc.get_func_name(fea)), []).append("%x %s" % (item, idc.GetDisasm(item)))
for k, v in hits.items():
    out.append(k); out.extend("    " + s for s in v[:6])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_ctx.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(hits))
