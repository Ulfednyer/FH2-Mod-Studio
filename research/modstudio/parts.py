import sqlite3
db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
for t in ("List_UpgradeCarBodyFrontBumper", "List_UpgradeCarBodyRearBumper", "List_UpgradeCarBodyHood", "List_UpgradeCarBodySideSkirt"):
    print(t, db.execute("SELECT Id,Level,IsStock,RequiresGraphics FROM %s WHERE CarBodyId=2177000" % t).fetchall())
print("wing", db.execute("SELECT Id,Level,IsStock,RequiresGraphics FROM List_UpgradeRearWing WHERE Ordinal=2177").fetchall())
print(db.execute("SELECT sql FROM sqlite_master WHERE name='List_UpgradeCarBodyFrontBumper'").fetchone()[0][:300])
print("bodies with visual front bumper rows", db.execute("SELECT COUNT(DISTINCT CarBodyId) FROM List_UpgradeCarBodyFrontBumper WHERE RequiresGraphics=1").fetchall())
