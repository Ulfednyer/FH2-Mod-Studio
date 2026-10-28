import os, sys
DIR = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql"
sys.path.insert(0, DIR)
from fh2sql import Conn

TABLES = ["List_UpgradeEngineTurboSingle", "List_UpgradeEngineTurboTwin", "List_UpgradeEngineTurboQuad"]
COLS = ["TorqueDropOffScale0", "TorqueDropOffScale1"]
SEL = 'SELECT rowid, %s FROM "%s" ORDER BY rowid;'
c = Conn()


def snapshot(t):
    r = c.call(SEL % (", ".join(COLS), t))
    if r["error"]:
        sys.exit("%s: %s" % (t, r["error"]))
    return r["results"][0]["rows"]


def stats(rows, i):
    vals = [float(r[i]) for r in rows if r[i] is not None]
    return "n=%d min=%g max=%g avg=%.4f" % (len(vals), min(vals), max(vals), sum(vals) / len(vals)) if vals else "n=0"


mode = sys.argv[1]
if mode == "backup":
    backup = os.path.join(DIR, "restore_turbo_dropoff.sql")
    if os.path.exists(backup):
        sys.exit("restore file already exists; refusing to overwrite original values")
    with open(backup, "w") as fh:
        fh.write("-- original TorqueDropOffScale values (run with: python fh2sql.py -f restore_turbo_dropoff.sql)\n")
        for t in TABLES:
            rows = snapshot(t)
            print("%-30s %s | %s" % (t, stats(rows, 1), stats(rows, 2)))
            for r in rows:
                sets = ", ".join("%s=%s" % (col, "NULL" if v is None else repr(float(v))) for col, v in zip(COLS, r[1:]))
                fh.write('UPDATE "%s" SET %s WHERE rowid=%s;\n' % (t, sets, r[0]))
    print("wrote", backup)
elif mode == "apply":
    sql = "".join('UPDATE "%s" SET %s;' % (t, ", ".join("%s = %s * 2" % (col, col) for col in COLS)) for t in TABLES)
    sql += " SELECT total_changes();"
    r = c.call(sql)
    print("error:", r["error"])
elif mode == "verify":
    for t in TABLES:
        rows = snapshot(t)
        print("%-30s %s | %s" % (t, stats(rows, 1), stats(rows, 2)))
