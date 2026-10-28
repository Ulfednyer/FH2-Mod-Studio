import idautils, idc, idaapi, ida_funcs, ida_name, ida_hexrays, ida_bytes, re, struct
try:
    ida_hexrays.init_hexrays_plugin()
except Exception:
    pass

# 1) command-line keys near the parsers
cl = []
for s in idautils.Strings():
    a = int(s.ea)
    if (0x141FF9000 <= a <= 0x141FFB000) or (0x141E05000 <= a <= 0x141E06000):
        t = str(s)
        if 2 <= len(t) <= 60:
            cl.append("%X:%s" % (a, t))
print("CMDLINE(%d): " % len(cl) + " | ".join(cl[:150]))
print()

targets = ["sub_1404A6F20", "sub_140219270", "sub_1400D49B0", "sub_1400DEB20",
           "sub_1400DEFD0", "sub_141039420", "sub_141038A20", "sub_1400C7460", "sub_1401C2B00"]
kw = re.compile(r'(lod|dist|far|fade|bias|scale|stream|range|radius|visib|cull|"|\d+\.\d+|0\.\d+)', re.I)
hexre = re.compile(r'0x14[0-9A-Fa-f]{5,7}')

for tn in targets:
    ea = int(tn[4:], 16)
    f = ida_funcs.get_func(ea)
    if not f:
        print("## %s no func" % tn)
        continue
    name = ida_name.get_name(f.start_ea) or tn
    try:
        cf = ida_hexrays.decompile(f.start_ea)
        txt = str(cf).splitlines()
    except Exception as e:
        print("## %s decompile fail %s" % (name, e))
        continue
    print("## %s @%X lines=%d" % (name, f.start_ea, len(txt)))
    n = 0
    floats = []
    for ln in txt:
        if kw.search(ln):
            print("  " + ln.strip()[:150])
            n += 1
            if n >= 28:
                print("  ...")
                break
        for h in hexre.findall(ln):
            v = int(h, 16)
            try:
                b = ida_bytes.get_bytes(v, 4)
                if b:
                    floats.append("%s=%g" % (h, struct.unpack('<f', b)[0]))
            except Exception:
                pass
    if floats:
        print("  FLOATS: " + " ".join(sorted(set(floats))[:20]))
