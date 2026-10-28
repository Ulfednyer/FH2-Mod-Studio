import idc, idautils, ida_nalt, ida_funcs, re
out = []
mods = {}
def cb(ea, name, ordinal):
    mods.setdefault(cur, []).append((ea, name or "#%d" % ordinal))
    return True
for i in range(ida_nalt.get_import_module_qty()):
    cur = ida_nalt.get_import_module_name(i)
    ida_nalt.enum_import_names(i, cb)
pat = re.compile(r"Find|File|Directory|Path|Volume|Package|Storage|Attributes", re.I)
for m, items in mods.items():
    hits = [(ea, n) for ea, n in items if pat.search(n)]
    out.append("%s: %d imports, file-ish: %s" % (m, len(items), [n for _, n in hits]))
    for ea, n in hits:
        if re.search(r"FindFirst|FindNext|GetFileAttributes|CreateFile|GetFileInformationByHandle|FindClose", n):
            callers = sorted({idc.get_func_name(x.frm) for x in idautils.XrefsTo(ea)})
            out.append("   %s @%x callers: %s" % (n, ea, callers[:12]))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_imp.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(mods))
