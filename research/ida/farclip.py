# Runs inside IDA. Verify the CamFarClip global: static value, writers/readers, and the code that sets it.
import struct
import idautils, idc, ida_funcs, ida_name, ida_bytes, ida_hexrays

G = 0x142E77568
print("static value:", struct.unpack("<f", ida_bytes.get_bytes(G, 4))[0], "seg:", idc.get_segm_name(G))
for x in idautils.XrefsTo(G):
    f = ida_funcs.get_func(x.frm)
    print("  %X %-6s %-40s in %s" % (x.frm, "write" if x.type == 3 else "read", idc.generate_disasm_line(x.frm, 0)[:40], ida_name.get_name(f.start_ea) if f else "?"))
lines = str(ida_hexrays.decompile(0x141038A20)).splitlines()
for i, l in enumerate(lines):
    if "CamFarClip" in l or "dword_142E77568" in l or "BumperHighCam" in l:
        print("   " + " | ".join(s.strip() for s in lines[max(0, i - 1): i + 2]))
