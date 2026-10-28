# IDAPython: functions that read the steering block's fields (car+0x5C: +0 MaxAngle, +4 Filtered, +1C MaxGees,
# +20 MinMaxAngle, +24 SlowSpeed, +28 FastSpeed, +2C FastRateScale) as floats from one base register.
import re
import idautils
import idc

WANT = {0x1C, 0x20, 0x24, 0x28}
out = []
seg = next(s for s in idautils.Segments() if idc.get_segm_name(s) == ".text")
for f in idautils.Functions(seg, idc.get_segm_end(seg)):
    if idc.get_func_attr(f, idc.FUNCATTR_END) - f > 0x4000:
        continue
    seen = {}
    for ea in idautils.FuncItems(f):
        m = idc.print_insn_mnem(ea)
        if not m.startswith("v") or "ss" not in m:
            continue
        for op in (0, 1, 2):
            t = idc.print_operand(ea, op)
            mm = re.fullmatch(r"(?:dword ptr )?\[(r\w+)\+([0-9A-F]+)h\]", t)
            if mm:
                seen.setdefault(mm.group(1), set()).add(int(mm.group(2), 16))
    for reg, offs in seen.items():
        if WANT <= offs:
            out.append((hex(f), idc.get_func_name(f), reg, sorted(hex(o) for o in offs if o <= 0x40)))
for o in out[:40]:
    print(o)
print(len(out))
