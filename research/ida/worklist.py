# Runs inside IDA. Builds worklist.json: unique physics/vehicle virtual functions, thunks resolved, with sizes.
import json, os, re
from collections import Counter
import ida_funcs, ida_name, ida_ua, idautils, idc, ida_loader

HERE = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad"
SRC = os.path.join(os.path.dirname(idc.get_idb_path()), "rtti_classes.json")
KEY = re.compile(r"Physic|Driveline|Turbo|Tire|Tyre|Engine|Suspension|Transmission|Gearbox|Clutch|Brake|Aero|Differential|Damper|Spring|Torque|Drivetrain|Wheel|Chassis|Steering|Boost|Rpm", re.I)
SKIP = re.compile(r"^(std|Concurrency|Windows|AVUI|Platform|Xls)::|<")
OURS = re.compile(r"::(off[0-9A-F]+_)?vf[0-9A-F]{2}$")

ida_loader.save_database(idc.get_idb_path(), 0)


def resolve(ea):
    f = ida_funcs.get_func(ea)
    if f and f.end_ea - f.start_ea <= 0x20:
        for head in idautils.Heads(f.start_ea, f.end_ea):
            insn = ida_ua.insn_t()
            if ida_ua.decode_insn(insn, head) and insn.get_canon_mnem() in ("jmp", "call"):
                t = insn.Op1.addr
                if ida_funcs.get_func(t) and t != f.start_ea:
                    return t
    return ea


recs = [r for r in json.load(open(SRC)) if KEY.search(r["class"]) and not SKIP.search(r["class"])]
work, seen = [], set()
for r in recs:
    for slot, fs in enumerate(r["funcs"]):
        ea = resolve(int(fs, 16))
        if ea in seen:
            continue
        seen.add(ea)
        name = ida_name.get_name(ea)
        if not (OURS.search(name) or name.startswith("sub_")):
            continue
        f = ida_funcs.get_func(ea)
        work.append({"addr": hex(ea), "name": name, "class": r["class"], "slot": slot, "bases": r["bases"][:3],
                     "size": (f.end_ea - f.start_ea) if f else 0})
json.dump(work, open(os.path.join(HERE, "worklist.json"), "w"), indent=0)
cls = Counter(w["class"] for w in work)
print("classes:", len({r["class"] for r in recs}), "funcs:", len(work), "total bytes:", sum(w["size"] for w in work))
print("top classes:", cls.most_common(40))
