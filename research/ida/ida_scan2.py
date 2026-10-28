import idautils, ida_funcs, ida_ua, idc, json, os, time
STATE = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_scan2_state.json"
st = json.load(open(STATE)) if os.path.exists(STATE) else {"i": 0, "hits": {}}
funcs = list(idautils.Functions())
t0 = time.time()
insn = ida_ua.insn_t()
i = st["i"]
STACK = (4, 5)  # rsp, rbp register numbers
while i < len(funcs) and time.time() - t0 < 45:
    fea = funcs[i]; i += 1
    if fea in (0x140F697B0, 0x140F514A0): continue
    for item in idautils.FuncItems(fea):
        if ida_ua.decode_insn(insn, item) <= 0: continue
        for op in insn.ops:
            if op.type == ida_ua.o_void: break
            if op.type == ida_ua.o_displ and 0x5080 <= op.addr <= 0x50E0 and op.reg not in STACK:
                st["hits"].setdefault("%x" % fea, []).append("%x %s" % (item, idc.GetDisasm(item)))
st["i"] = i
json.dump(st, open(STATE, "w"))
print("func %d / %d, %d hit, done=%s" % (i, len(funcs), len(st["hits"]), i >= len(funcs)))
