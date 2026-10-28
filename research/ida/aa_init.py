# Runs inside IDA. ctor sub_1410B0390 -> class vftable -> slot 7 (renderer Init(w, h, ?, DXGI_SAMPLE_DESC)).
import re
import idautils, idc, ida_name, ida_hexrays, ida_bytes

ctor = str(ida_hexrays.decompile(0x1410B0390))
vts = list(dict.fromkeys(re.findall(r"=\s*(&?[\w:]+vftable)", ctor)))
print("ctor vftables:", vts)
vt = vts[0].lstrip("&")
vea = ida_name.get_name_ea(idc.BADADDR, vt)
init = ida_bytes.get_qword(vea + 56)
print("=== slot7 -> %s @%X" % (ida_name.get_name(init), init))
lines = [l for l in str(ida_hexrays.decompile(init)).splitlines() if l.strip() and "//" not in l.split(";")[0][:2]]
sig = next(l for l in lines if "(" in l and "__" in l)
print(sig)
a4 = sig.split("(", 1)[1].rstrip(")").split(",")[-1].split()[-1].strip("*")
print("4th arg:", a4, "| total lines:", len(lines))
for i, l in enumerate(lines):
    if re.search(r"\b%s\b|MultisampleQuality|SampleDesc|\b(4|8|16)u?\b.*[<>=]|[<>=].*\b(4|8|16)u?\)" % re.escape(a4), l):
        print("  %4d: %s" % (i, l.strip()[:160]))
