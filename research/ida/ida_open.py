import idc, idautils, ida_name, ida_bytes, ida_hexrays, re
out = []
# vtables whose slot 0x210/8 is a function: candidates for the "mount zip" virtual
cands = []
for ea, name in idautils.Names():
    if "vftable" in name or "vtbl" in name.lower():
        tgt = ida_bytes.get_qword(ea + 0x210)
        fn = idc.get_func_name(tgt)
        if fn and re.search(r"zip|file|fs|archive|mount|device|stream", name + fn, re.I):
            cands.append((name, fn, tgt))
for c in cands[:40]:
    out.append("%s slot0x210 -> %s %x" % c)
# strings used by zip readers (version / method checks)
for s in (b"Unsupported zip", b"zip version", b"bad zip", b"central directory", b"PK\x01\x02", b"Zip file"):
    ea = ida_bytes.find_bytes(s, 0x141E00000)
    if ea != idc.BADADDR:
        out.append("string %r at %x refs %s" % (s, ea, [hex(x.frm) for x in idautils.XrefsTo(ea)][:5]))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_open.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(cands))
