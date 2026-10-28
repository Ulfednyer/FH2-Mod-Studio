# Runs inside IDA. Prints callers of sqlite3ErrStr with size and callees, decompiling the small ones.
import idautils, idc, ida_funcs, ida_name, ida_hexrays

ERRSTR = 0x14007B5A0
for c in sorted({ida_funcs.get_func(x).start_ea for x in idautils.CodeRefsTo(ERRSTR, 0) if ida_funcs.get_func(x)}):
    f = ida_funcs.get_func(c)
    size = f.end_ea - f.start_ea
    calls = sorted({idc.get_operand_value(h, 0) for h in idautils.FuncItems(c) if idc.print_insn_mnem(h) == "call"})
    print("== %X %s size=%d calls=%s" % (c, ida_name.get_name(c), size, ["%X" % t for t in calls][:8]))
    if size < 0x90:
        print("\n".join(l for l in str(ida_hexrays.decompile(c)).splitlines() if l.strip() and "//" not in l))
