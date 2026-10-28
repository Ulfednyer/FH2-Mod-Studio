import sqlite3, json
db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
q = lambda s: db.execute(s).fetchall()
print("compounds:", q("SELECT * FROM List_TireCompound"))
print("TireCompound cols:", [r[1] for r in db.execute("PRAGMA table_info(List_UpgradeTireCompound)")])
for t, k, v in [("List_UpgradeTireCompound", "Ordinal", 2177), ("List_UpgradeSpringDamper", "Ordinal", 2177),
                ("List_UpgradeAntiSwayFront", "Ordinal", 2177), ("List_UpgradeAntiSwayRear", "Ordinal", 2177),
                ("List_UpgradeCarBodyTireWidthFront", "CarBodyId", 2177000), ("List_UpgradeCarBodyTireWidthRear", "CarBodyId", 2177000),
                ("List_UpgradeRimSizeFront", "Ordinal", 2177)]:
    print(t, q('SELECT Id, Level, IsStock FROM "%s" WHERE %s=%d ORDER BY Level' % (t, k, v)))
print("SpringDamper cols:", [r[1] for r in db.execute("PRAGMA table_info(List_UpgradeSpringDamper)")])
print("TireWidth cols:", [r[1] for r in db.execute("PRAGMA table_info(List_UpgradeCarBodyTireWidthFront)")])
print("TrackOffsets Z06:", q("SELECT * FROM CarTrackOffsets WHERE Id=2177"))
print("TrackOffsets sample:", q("SELECT * FROM CarTrackOffsets LIMIT 4"))
# any table referencing the compound or levels
for (n,) in q("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%Compound%' OR name LIKE '%TrackOffset%' OR name LIKE '%Spacer%' OR name LIKE '%UpgradeLevel%' OR name LIKE '%Tier%')"):
    print("table:", n, [r[1] for r in db.execute('PRAGMA table_info("%s")' % n)])
s = json.load(open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\FH2ModStudio\bin\Release\net9.0-windows\win-x64\FH2ModStudio.settings.json"))
for m in s.get("DbMods", []):
    print("MOD", m.get("Name"), "\n", (m.get("Sql") or "")[:3000])
