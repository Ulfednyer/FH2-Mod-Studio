# Runs inside IDA. Applies renames_a.tsv + renames_b.tsv (addr, name, confidence, reason); only overwrites mechanical names.
import os, re
import ida_funcs, ida_name, idautils, idc, ida_loader

HERE = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad"
FLAGS = ida_name.SN_NOWARN | ida_name.SN_NOCHECK | ida_name.SN_FORCE
MECH = re.compile(r"(::(off[0-9A-F]+_)?vf[0-9A-F]{2}$)|^sub_")
VALID = re.compile(r"^[A-Za-z_][A-Za-z0-9_:]*::[A-Za-z_~][A-Za-z0-9_]*$")

ok, skipped = 0, []
for tag in ("a", "b"):
    p = os.path.join(HERE, "renames_%s.tsv" % tag)
    if not os.path.exists(p):
        continue
    for line in open(p, encoding="utf-8-sig"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2 or not parts[0].startswith("0x"):
            continue
        ea, new = int(parts[0], 16), parts[1].strip()
        cur = ida_name.get_name(ea)
        cross_class = not cur.startswith("sub_") and cur.rsplit("::", 1)[0] != new.rsplit("::", 1)[0]
        folded = sum(1 for _ in idautils.DataRefsTo(ea)) > 6
        if not ida_funcs.get_func(ea) or not MECH.search(cur) or not VALID.match(new) or cross_class or folded:
            skipped.append("%s %s -> %s" % (parts[0], cur, new))
            continue
        ida_name.set_name(ea, new, FLAGS)
        if len(parts) >= 4 and not idc.get_func_cmt(ea, 0):
            idc.set_func_cmt(ea, "[%s] %s (was %s)" % (parts[2], parts[3], cur), 0)
        ok += 1
ida_loader.save_database(idc.get_idb_path(), 0)
print("applied %d, skipped %d" % (ok, len(skipped)))
print("\n".join(skipped[:30]))
