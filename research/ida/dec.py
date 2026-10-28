# Runs inside IDA. Decompiles every address listed in dec_in.txt (one hex addr per line, '#' comments ok).
import os, re
import ida_funcs, ida_hexrays, ida_name

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad"
MAX_LINES = 110

for line in open(os.path.join(HERE, "dec_in.txt")):
    line = line.split("#")[0].strip()
    if not line:
        continue
    ea = int(line, 16)
    f = ida_funcs.get_func(ea)
    print("==== %s %s" % (line, ida_name.get_name(ea)))
    if not f:
        print("  <no function>")
        continue
    try:
        text = str(ida_hexrays.decompile(f.start_ea))
    except Exception as e:
        print("  <decompile failed: %s>" % e)
        continue
    lines = [l for l in text.splitlines() if l.strip() and not re.match(r"\s*//", l)]
    print("\n".join(lines[:MAX_LINES]) + ("\n  ... (%d more lines)" % (len(lines) - MAX_LINES) if len(lines) > MAX_LINES else ""))
