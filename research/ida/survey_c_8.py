import idautils, idc, ida_funcs, ida_name, ida_hexrays, ida_bytes, re, struct
hexre = re.compile(r'0x14[0-9A-Fa-f]{5,7}')
kw = re.compile(r'(dword_|qword_|unk_|xmm|LOD|Dist|Scale|Bias|Thresh|min|max|"|float)', re.I)

def dec(ea, cap=12):
    f = ida_funcs.get_func(ea)
    if not f:
        print("## %X nofunc" % ea)
        return
    try:
        txt = str(ida_hexrays.decompile(f.start_ea)).splitlines()
    except Exception:
        print("## %X decompile fail" % ea)
        return
    print("## %s @%X lines=%d" % (ida_name.get_name(f.start_ea), f.start_ea, len(txt)))
    n = 0
    for ln in txt:
        if kw.search(ln) and '=' in ln:
            print("  " + ln.strip()[:120])
            n += 1
            if n >= cap:
                break
    fl = []
    for ln in txt:
        for h in hexre.findall(ln):
            try:
                b = ida_bytes.get_bytes(int(h, 16), 4)
                if b:
                    fl.append("%s=%g" % (h, struct.unpack('<f', b)[0]))
            except Exception:
                pass
    if fl:
        print("  FLOATS: " + " ".join(sorted(set(fl))[:12]))

for ea in [0x1412FFA90, 0x1412FF980, 0x1412FF8C0, 0x1412FF820, 0x1412FFCA0, 0x1412FF500, 0x1412FFBE0]:
    dec(ea)
