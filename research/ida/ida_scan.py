import idautils, ida_funcs, ida_ua, json, os, time
STATE = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\ida_scan_state.json"
DISPS = {0x50AC: "stockNorm", 0x50B0: "fitNorm", 0x50B4: "w0", 0x50B8: "w3", 0x50BC: "stockFW", 0x50C0: "stockRW",
         0x50C4: "FrontOff", 0x50C8: "RearOff", 0x50CC: "UpgFront", 0x50D0: "UpgRear", 0x50D9: "aftermarketFlag"}
st = json.load(open(STATE)) if os.path.exists(STATE) else {"i": 0, "hits": {}}
funcs = list(idautils.Functions())
t0 = time.time()
insn = ida_ua.insn_t()
i = st["i"]
while i < len(funcs) and time.time() - t0 < 45:
    f = ida_funcs.get_func(funcs[i])
    i += 1
    if not f or f.start_ea in (0x140F697B0, 0x140F514A0):
        continue
    for item in idautils.FuncItems(f.start_ea):
        if ida_ua.decode_insn(insn, item) <= 0:
            continue
        for op in insn.ops:
            if op.type == ida_ua.o_void: break
            if op.type == ida_ua.o_displ and op.addr in DISPS:
                lst = st["hits"].setdefault("%x" % f.start_ea, [])
                if DISPS[op.addr] not in lst: lst.append(DISPS[op.addr])
st["i"] = i
json.dump(st, open(STATE, "w"))
print("func %d / %d, %d funcs hit, done=%s" % (i, len(funcs), len(st["hits"]), i >= len(funcs)))
