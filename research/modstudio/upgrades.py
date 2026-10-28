import re, sqlite3

db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
q = lambda s: db.execute(s).fetchall()
cols = lambda t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]

for t in ["List_UpgradeCarBodyTireWidthFront", "List_UpgradeCarBodyTireWidthRear", "List_UpgradeCarBody", "List_UpgradeCarBodyWeight", "List_UpgradeCarBodyChassisStiffness"]:
    print(t, cols(t))
    print("   Z06:", q("SELECT * FROM %s WHERE %s LIMIT 4" % (t, "Ordinal=2177" if "Ordinal" in cols(t) else "1=1")))
print("\nCarBody: how do body-part tables link? CarBodyID for Z06:", q("SELECT CarBodyID FROM List_UpgradeCarBody WHERE Ordinal=2177"))
print("TireWidthFront rows with CarBodyID 2177000:", q("SELECT * FROM List_UpgradeCarBodyTireWidthFront WHERE CarBodyID=2177000"))
print("\ncolumns anywhere matching track/offset/spacer/wheelbase/pivot:")
for (n,) in q("SELECT name FROM sqlite_master WHERE type='table'"):
    hits = [c for c in cols(n) if re.search(r"track|offset|spacer|wheelbase|pivot|halfwidth|width", c, re.I)]
    if hits:
        print("  %-38s %s" % (n, hits))
print("\nZ06 spring physics pivots:", q("SELECT SpringDamperPhysicsID, ChassisPivotX, ChassisPivotY, TirePivotX FROM List_SpringDamperPhysics WHERE Ordinal=2177"))
print("TirePivotX spread across cars:", q("SELECT MIN(TirePivotX), AVG(TirePivotX), MAX(TirePivotX) FROM List_SpringDamperPhysics"))
print("engines Z06 could swap to (V8 donors with full part sets), sample:",
      q("SELECT e.EngineID, e.MediaName, e.ConfigID, e.CylinderID FROM Data_Engine e WHERE e.CylinderID IN (SELECT CylinderID FROM Data_Engine WHERE EngineID=2305) LIMIT 8"))
