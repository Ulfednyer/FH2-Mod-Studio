# Runs inside IDA. Maps sqlite3_column_* wrappers: callers of columnMem (0x140020480) and the value accessor each calls.
import idautils, idc, ida_funcs, ida_name, ida_hexrays

COLUMN_MEM = 0x140020480
callers = sorted({ida_funcs.get_func(x).start_ea for x in idautils.CodeRefsTo(COLUMN_MEM, 0) if ida_funcs.get_func(x)})
accessors = set()
for c in callers:
    calls = [idc.get_operand_value(h, 0) for h in idautils.FuncItems(c) if idc.print_insn_mnem(h) == "call"]
    acc = [t for t in calls if t not in (COLUMN_MEM, 0x140020530)]
    accessors.update(acc)
    print("%X %-28s -> %s" % (c, ida_name.get_name(c), ["%X" % a for a in acc]))
print("--- accessor bodies")
for a in sorted(accessors):
    lines = [l for l in str(ida_hexrays.decompile(a)).splitlines() if l.strip() and "//" not in l]
    print("%X (%d lines): %s" % (a, len(lines), " ".join(l.strip() for l in lines[1:9])[:260]))
