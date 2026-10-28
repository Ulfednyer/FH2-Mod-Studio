import ida_hexrays
t = str(ida_hexrays.decompile(0x140F697B0))
i = t.find('WheelNormOffsets WHERE Id=%d", v7')
open(r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_offsets2.txt", "w", encoding="utf-8").write(t[i:])
print(len(t))
