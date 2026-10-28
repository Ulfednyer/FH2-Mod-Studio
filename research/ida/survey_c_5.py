import idautils, idc, ida_funcs, ida_name, ida_hexrays, ida_bytes, re, struct
hexre = re.compile(r'0x14[0-9A-Fa-f]{5,7}')
kw = re.compile(r'(lod|dist|grass|ambient|crowd|stream|chunk|far|fade|scale|bias|"|\d+\.\d+|0\.\d+|1000|200)', re.I)

def find_str(sub):
    for s in idautils.Strings():
        if str(s) == sub:
            return s.ea
    return None

def dec(ea, label, cap=18):
    f = ida_funcs.get_func(ea)
    if not f:
        print("## %s nofunc" % label)
        return
    try:
        txt = str(ida_hexrays.decompile(f.start_ea)).splitlines()
    except Exception as e:
        print("## %s decompile fail" % label)
        return
    print("## %s %s @%X lines=%d" % (label, ida_name.get_name(f.start_ea), f.start_ea, len(txt)))
    n = 0
    fl = []
    for ln in txt:
        if kw.search(ln):
            print("  " + ln.strip()[:130])
            n += 1
            if n >= cap:
                break
        for h in hexre.findall(ln):
            try:
                b = ida_bytes.get_bytes(int(h, 16), 4)
                if b:
                    fl.append("%s=%g" % (h, struct.unpack('<f', b)[0]))
            except Exception:
                pass
    if fl:
        print("  FLOATS: " + " ".join(sorted(set(fl))[:14]))

dec(0x140F40340, "DistanceToGrassCost")
dec(0x140F92790, "GeoChunk")
for key in ["disableambienttrees", "keepLOD0Car", "ForceCrowdModels", "autovistaLOD0", "streamsize"]:
    ea = find_str(key)
    if ea is None:
        print("## %s not found" % key)
        continue
    for x in idautils.XrefsTo(ea):
        f = ida_funcs.get_func(x.frm)
        if f:
            dec(f.start_ea, "cmd:" + key, cap=10)
            break
