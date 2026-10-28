import re, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql")
from fh2sql import Conn

c = Conn()


def one(sql):
    r = c.call(sql)
    return (r["results"][0] if r["results"] else None), r["error"]


tables = c.call("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name;")["results"][0]["rows"]
for key in ("EngineID", "DrivetrainID", "TireCompoundID", "AeroPhysicsID", "MakeID"):
    hits = [n for n, s in tables if re.search(r"\b%s\b" % key, s or "", re.I)]
    print("%s used in: %s" % (key, ", ".join(hits)))
print()
for t, where in [("Data_Engine", "EngineID = 2166"), ("Data_Drivetrain", "DrivetrainID = 2113"),
                 ("List_UpgradeEngineTurboSingle", "EngineID = 2166"), ("List_UpgradeEngineFlywheel", "EngineID = 2166"),
                 ("List_UpgradeDrivetrainClutch", "DrivetrainID = 2113"), ("List_UpgradeTransmission", "DrivetrainID = 2113")]:
    r, err = one('SELECT * FROM "%s" WHERE %s;' % (t, where))
    if err:
        print("%s: %s" % (t, err))
        continue
    print("%s: %d row(s); cols(%d): %s" % (t, len(r["rows"]), len(r["columns"]), ", ".join(r["columns"])))
    if r["rows"]:
        print("   first: " + ", ".join(str(v) for v in r["rows"][0])[:300])
mk, err = one("SELECT * FROM List_CarMake WHERE ID = 54;")
print("\nList_CarMake:", err or (mk["columns"], mk["rows"][:1]))
