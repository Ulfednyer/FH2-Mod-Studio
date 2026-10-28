# Runs inside IDA. Prints decompiled lines matching a regex (with context) for selected functions.
import re
import ida_hexrays, ida_name, idc

vt = ida_name.get_name_ea(idc.BADADDR, "AppCommandLineParameters::vftable")
JOBS = [
    (idc.get_qword(vt + 3 * 8), r"cmdlinedottxt|sub_14107C340", 6),
]
for ea, pat, ctx in JOBS:
    cf = ida_hexrays.decompile(ea)
    lines = str(cf).splitlines()
    hits = [i for i, l in enumerate(lines) if re.search(pat, l)]
    keep = sorted({j for i in hits for j in range(max(0, i - 4), min(len(lines), i + ctx + 1))})
    print("==== %s (%d lines)" % (ida_name.get_name(cf.entry_ea), len(lines)))
    prev = -2
    for j in keep:
        if j != prev + 1:
            print("  ...")
        print(lines[j])
        prev = j
