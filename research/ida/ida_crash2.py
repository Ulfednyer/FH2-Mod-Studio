import ida_hexrays, re, idc
t = str(ida_hexrays.decompile(0x140FD1600))
lines = t.splitlines()
out = []
for i, l in enumerate(lines):
    if re.search(r"528LL|\"path\"|\"dirstart\"|\"priority\"|zipmanifest|ZipFiles|direntries", l):
        out.append("\n".join("%4d %s" % (k, lines[k]) for k in range(max(0, i - 6), min(len(lines), i + 8))))
        out.append("-----")
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_crash2.txt", "w", encoding="utf-8").write("\n".join(out))
print(len(lines))
