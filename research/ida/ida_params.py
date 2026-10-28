import idc, idautils, ida_hexrays, ida_bytes, ida_funcs, re
out = []
factories = {0: 0x1410AE580, 1: 0x1410ADE40, 2: 0x1410ADEE0, 3: 0x1410ADD00, 4: 0x1410AE0D0, 5: 0x1410AE3D0,
             6: 0x1410AE470, 7: 0x1410AE330, 8: 0x1410ADDA0, 9: 0x1410ADF80, 11: 0x1410AE4E0}
for typ, fac in sorted(factories.items()):
    t = str(ida_hexrays.decompile(fac))
    vts = re.findall(r"&(\w+::vftable|off_[0-9A-F]+|\w+_vftable\w*)", t)
    # fall back: find lea of a vtable in disassembly
    vt = None
    for ea in idautils.FuncItems(fac):
        if idc.print_insn_mnem(ea) == "lea":
            op = idc.get_operand_value(ea, 1)
            nm = idc.get_name(op) or ""
            if "vftable" in nm or nm.startswith("off_"):
                vt = op
    out.append("==== type %d factory %x vtables %s chosen %s" % (typ, fac, vts[:4], idc.get_name(vt) if vt else None))
    if not vt:
        continue
    for slot in (1, 2):
        f = ida_bytes.get_qword(vt + slot * 8)
        try:
            body = str(ida_hexrays.decompile(f))
        except Exception as e:
            body = "fail %s" % e
        calls = re.findall(r"\+ (\d+)LL\)\)\(([^;]{0,120})", body)
        out.append("  slot %d %x %s len %d" % (slot, f, idc.get_func_name(f), len(body)))
        out.append("    stream calls: " + "; ".join("+%s(%s)" % (o, a.strip()[:70]) for o, a in calls[:20]))
        if slot == 1:
            out.append("\n".join("    | " + l for l in body.splitlines() if not re.match(r"\s+\S.*; // ", l))[:2500])
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_params.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
