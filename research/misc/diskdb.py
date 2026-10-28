import sqlite3

db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
cur = db.cursor()


def show(sql, limit=3):
    try:
        r = cur.execute(sql)
    except Exception as e:
        print("  ERR", e)
        return
    cols = [d[0] for d in r.description]
    rows = r.fetchmany(limit)
    print("  cols: " + ", ".join(cols))
    for row in rows:
        print("   ", ", ".join(str(v) for v in row)[:260])


for t, w in [("List_UpgradeDrivetrainTransmission", "DrivetrainID=2113"), ("List_UpgradeDrivetrainDifferential", "DrivetrainID=2113"),
             ("List_UpgradeDrivetrainDriveline", "DrivetrainID=2113"), ("Powertrains", "1=1"), ("List_TireCompound", "1=1"),
             ("List_AeroPhysics", "1=1"), ("List_UpgradeEngineCamshaft", "EngineID=2166"), ("List_UpgradeEngineDisplacement", "EngineID=2166")]:
    print(t)
    show("SELECT * FROM %s WHERE %s" % (t, w), 2)
print("\nlookup tables:")
for (n,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'List_%Type%' OR name LIKE 'List_Drive%' OR name LIKE 'List_Car%' OR name LIKE 'List_Aspiration%' OR name LIKE 'List_Engine%' OR name LIKE 'List_Class%' OR name LIKE 'List_Cylinder%') ORDER BY name").fetchall():
    cnt = cur.execute('SELECT COUNT(*) FROM "%s"' % n).fetchone()[0]
    cols = [d[1] for d in cur.execute('PRAGMA table_info("%s")' % n).fetchall()]
    print("  %-34s rows=%-4s %s" % (n, cnt, cols[:6]))
print("\nDriveTypeID values:", cur.execute("SELECT DriveTypeID, COUNT(*) FROM Data_Car GROUP BY 1").fetchall())
print("Data_Drivetrain DrivetypeID:", cur.execute("SELECT DrivetypeID, COUNT(*) FROM Data_Drivetrain GROUP BY 1").fetchall())
print("ClassID:", cur.execute("SELECT ClassID, COUNT(*) FROM Data_Car GROUP BY 1").fetchall())
print("AspirationTypeId:", cur.execute("SELECT AspirationTypeId, COUNT(*) FROM Data_Car GROUP BY 1").fetchall())
print("EnginePlacementID:", cur.execute("SELECT EnginePlacementID, COUNT(*) FROM Data_Car GROUP BY 1").fetchall())
print("cars:", cur.execute("SELECT COUNT(*) FROM Data_Car").fetchone(), "with media:", cur.execute("SELECT COUNT(*) FROM Data_Car WHERE MediaName <> ''").fetchone())
