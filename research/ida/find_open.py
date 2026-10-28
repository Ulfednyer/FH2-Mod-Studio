# Runs inside IDA. Finds sqlite openDatabase via its "RTRIM" collation string, walks callers up to game code,
# and locates the App singleton (stores of App's vftable / globals referenced next to it).
import idautils, idc, ida_funcs, ida_name, ida_bytes


def fname(ea):
    f = ida_funcs.get_func(ea)
    return ("%s@%X" % (ida_name.get_name(f.start_ea), f.start_ea)) if f else "?@%X" % ea


def callers(fea):
    return sorted({ida_funcs.get_func(x).start_ea for x in idautils.CodeRefsTo(fea, 0) if ida_funcs.get_func(x)})


for s in idautils.Strings():
    if str(s) == "RTRIM":
        for x in idautils.XrefsTo(s.ea):
            od = ida_funcs.get_func(x.frm).start_ea
            print("openDatabase? %s" % fname(od))
            for c in callers(od):
                print("  <- %s (%d bytes)" % (fname(c), ida_funcs.get_func(c).end_ea - c))
                for cc in callers(c)[:8]:
                    print("      <- %s" % fname(cc))
                    for ccc in callers(cc)[:6]:
                        print("          <- %s" % fname(ccc))

app_vt = ida_name.get_name_ea(idc.BADADDR, "App::vftable")
print("App::vftable = %X" % app_vt)
for x in idautils.XrefsTo(app_vt):
    print("  App vftable ref in %s" % fname(x.frm))
# Who reads App+0x40 through a global? find globals holding App* = qword vars written in App ctor callers
