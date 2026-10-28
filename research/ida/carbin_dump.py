import idc, ida_hexrays, re
OUT=r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\carbin\decomp.txt"
fs=[0x1411af870,0x1411afec0,0x1411692E0,0x1411b0140,0x1411ad6c0,0x1411CB3D0,0x14116A380]
with open(OUT,'w') as o:
    for f in fs:
        try: s=str(ida_hexrays.decompile(f))
        except Exception as e: s=str(e)
        o.write('\n===== %x %s\n'%(f,idc.get_func_name(f))); o.write(s)
print('ok')
