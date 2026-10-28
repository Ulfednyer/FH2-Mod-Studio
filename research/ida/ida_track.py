import idc, idautils, ida_funcs, ida_bytes, ida_hexrays, ida_segment
out = []
def strea(s):
    ea = ida_bytes.find_bytes(s.encode() + b"\0", 0x141E00000)
    while ea != idc.BADADDR and ida_bytes.get_byte(ea - 1) != 0:
        ea -= 1
    return ea
funcs = set()
for s in ["ModelFrontTrackOuter", "ModelRearTrackOuter", "TrackWidth"]:
    ea = ida_bytes.find_bytes(s.encode(), 0x141E00000)
    # find containing string start
    st = ea
    while ida_bytes.get_byte(st - 1) not in (0,): st -= 1
    out.append("%s @%x start %x: %s" % (s, ea, st, idc.get_strlit_contents(st, -1, 0)))
    for x in list(idautils.XrefsTo(st)) + list(idautils.XrefsTo(ea)):
        f = ida_funcs.get_func(x.frm)
        out.append("   xref %x %s" % (x.frm, idc.get_func_name(f.start_ea) if f else "?"))
        if f: funcs.add(f.start_ea)
for f in sorted(funcs):
    t = str(ida_hexrays.decompile(f))
    out.append("\n===== %x %s (%d chars) =====" % (f, idc.get_func_name(f), len(t)))
    for key in ("TrackOuter", "TrackWidth", "WheelDiameter", "RimSize"):
        i = t.find(key)
        while i >= 0 and len(out) < 400:
            out.append("...[%s]...\n%s" % (key, t[max(0, i - 900): i + 1600]))
            i = t.find(key, i + 2500)
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_track.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(funcs))
