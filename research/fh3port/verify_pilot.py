import sqlite3, zipfile, json, os, re
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
d = sqlite3.connect("file:%s?mode=ro" % (M + r"\stripped\gamedbRC.slt"), uri=True)
print("integrity:", d.execute("PRAGMA integrity_check").fetchone()[0], "header r/w:", open(M + r"\stripped\gamedbRC.slt", "rb").read(20)[18:20])
r = d.execute("SELECT Id, MediaName, DisplayName, ModelShort, MakeName, MakeID, BaseCost, ClassID, Thumbnail, IsPurchased, StockWheelID FROM Data_Car WHERE Id=2352").fetchone()
print("Data_Car:", r)
print("make row:", d.execute("SELECT * FROM List_CarMake WHERE ID=?", (r[5],)).fetchone())
eng = [x[0] for x in d.execute("SELECT EngineID FROM List_UpgradeEngine WHERE Ordinal=2352")]
print("engines:", eng, [d.execute("SELECT EngineID, MediaName FROM Data_Engine WHERE EngineID=?", (e,)).fetchone() for e in eng])
print("cam curves:", d.execute("SELECT EngineID, Level, TorqueCurveFullThrottleID, (SELECT COUNT(*) FROM List_TorqueCurve t WHERE t.TorqueCurveID = c.TorqueCurveFullThrottleID) FROM List_UpgradeEngineCamshaft c WHERE EngineID IN (%s)" % ",".join(map(str, eng))).fetchall())
print("tyres:", d.execute("SELECT Level, IsStock, TireCompoundID, TireModelName FROM List_UpgradeTireCompound WHERE Ordinal=2352 ORDER BY Level").fetchall())
print("susp types:", d.execute("SELECT DISTINCT p.SuspensionPhysicsTypeID, t.PhysicsXML FROM List_SpringDamperPhysics p LEFT JOIN List_SuspensionPhysicsType t ON t.SuspensionPhysicsTypeID=p.SuspensionPhysicsTypeID WHERE p.Ordinal=2352").fetchall() if "PhysicsXML" in [c[1] for c in d.execute("PRAGMA table_info(List_SuspensionPhysicsType)")] else d.execute("SELECT DISTINCT SuspensionPhysicsTypeID FROM List_SpringDamperPhysics WHERE Ordinal=2352").fetchall())
print("wheel:", d.execute("SELECT ID, MediaName FROM List_Wheels WHERE ID=?", (r[10],)).fetchone())
print("body:", d.execute("SELECT CarBodyID FROM List_UpgradeCarBody WHERE Ordinal=2352").fetchall(), "colors:", d.execute("SELECT COUNT(*) FROM Combo_Colors WHERE Ordinal=2352").fetchone())
man = open(M + r"\zipmanifest.xml", encoding="utf-8").read()
for p in ("cars\\acu_nsx_16.zip", "stripped\\rcfh3.zip", "cars\\_library\\textures.zip"):
    print("manifest:", [l.strip() for l in man.splitlines() if p in l.lower()])
print("manifest entries:", man.count("<Zip "), "well-formed end:", man.rstrip().endswith("</ZipFiles>"))
print("rcfh3:", zipfile.ZipFile(M + r"\stripped\RCFH3.zip").namelist())
tz = zipfile.ZipFile(M + r"\cars\_library\Textures.zip")
print("lib textures added:", [n for n in tz.namelist() if "acu_" in n.lower() or n.lower().endswith("plate_ao.swatchbin")])
j = json.load(open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\FH3Port_Backup\journal.json"))
print("backups:", list(j["backups"]), "created:", j["created"])
