# Runs inside IDA. Disassembly around gamedbRC string use + CDatabase constructor sites.
import idautils, idc, ida_funcs, ida_name

def window(ea, before=12, after=28):
    start = ea
    for _ in range(before):
        p = idc.prev_head(start)
        if p == idc.BADADDR:
            break
        start = p
    cur = start
    for _ in range(before + after):
        print("  %X  %s" % (cur, idc.generate_disasm_line(cur, 0)))
        cur = idc.next_head(cur)

print("=== uses of 'game:\\Media\\Stripped\\gamedbRC.slt'")
for x in idautils.XrefsTo(0x141FF97E8):
    window(x.frm)

for vt in (0x142E7AF18, 0x142E7B0B8):
    print("=== code refs to vftable %X (%s)" % (vt, ida_name.get_name(vt)))
    for x in idautils.XrefsTo(vt):
        f = ida_funcs.get_func(x.frm)
        print("  %X in %s" % (x.frm, ida_name.get_name(f.start_ea) if f else "?"))
