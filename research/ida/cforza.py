import idc, ida_name
for n in ("Frame11::vftable", "Frame::vftable"):
    print(n, "%X" % ida_name.get_name_ea(idc.BADADDR, n))
