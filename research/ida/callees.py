# Runs inside IDA. Lists direct callees (in call order) of a few functions.
import idautils, idc, ida_funcs, ida_name, ida_ua

for root in (0x14108FA20, 0x14108E900, 0x14108BCD0, 0x14108BF20):
    f = ida_funcs.get_func(root)
    seen = []
    for h in idautils.FuncItems(f.start_ea):
        if idc.print_insn_mnem(h) == "call":
            t = idc.get_operand_value(h, 0)
            if ida_funcs.get_func(t) and t not in seen:
                seen.append(t)
    print("%s @%X (%d bytes): %s" % (ida_name.get_name(root), root, f.end_ea - f.start_ea,
          ", ".join("%s" % ida_name.get_name(t) for t in seen)))
