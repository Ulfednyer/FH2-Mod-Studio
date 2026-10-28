# Runs inside IDA. Slot 0x1C (GetMotionBlurAmount) of every Camera::CCam* class: the global it returns + default.
import json, os, re, struct
import idc, ida_name, ida_hexrays, ida_bytes

recs = json.load(open(os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json")))
seen = set()
for r in recs:
    if not r["class"].startswith("Camera::CCam") or r["offset"] or len(r["funcs"]) <= 0x2F:
        continue
    ea = int(r["funcs"][0x1C], 16)
    if (r["class"], ea) in seen:
        continue
    seen.add((r["class"], ea))
    text = str(ida_hexrays.decompile(ea))
    m = re.search(r"(dword_[0-9A-F]+)", text)
    if m:
        g = ida_name.get_name_ea(idc.BADADDR, m.group(1))
        print("%-32s slot1C=%X -> %s default=%g" % (r["class"], ea, m.group(1), struct.unpack("<f", ida_bytes.get_bytes(g, 4))[0]))
    else:
        body = " ".join(l.strip() for l in text.splitlines()[2:8])
        print("%-32s slot1C=%X -> %s" % (r["class"], ea, body[:110]))
