import ida_hexrays, re
t = str(ida_hexrays.decompile(0x141056210))
out = []
i = t.find('"SELECT * FROM Data_CarBody WHERE ID="')
out.append(t[max(0, i - 200): i + 300])
# every line that assigns or uses v266
for m in re.finditer(r"[^\n]*\bv266\b[^\n]*", t):
    out.append("L: " + m.group().strip())
# all SQL strings in the function, in order
for m in re.finditer(r'"(SELECT[^"]*|[^"]*FROM [^"]*|[^"]*JOIN[^"]*|[^"]*WHERE[^"]*)"', t):
    out.append("SQL: " + m.group(1))
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_body.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
