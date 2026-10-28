import idautils, ida_funcs, ida_name, ida_hexrays

print(str(ida_hexrays.decompile(0x141086900)))
for x in idautils.CodeRefsTo(0x141086900, 0):
    f = ida_funcs.get_func(x)
    lines = str(ida_hexrays.decompile(f.start_ea)).splitlines()
    for i, l in enumerate(lines):
        if "sub_141086900" in l:
            print("== caller %s @%X" % (ida_name.get_name(f.start_ea), f.start_ea))
            print("\n".join(lines[max(0, i - 6): i + 2]))
