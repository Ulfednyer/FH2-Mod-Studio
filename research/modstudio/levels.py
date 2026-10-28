import sqlite3

db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
q = lambda s: db.execute(s).fetchall()
cols = lambda t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
tables = [r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'List_Upgrade%' ORDER BY name")]
print("%-38s %-10s %-34s %s" % ("table", "key", "levels (count)", "rows/key/level>1"))
for t in tables:
    c = cols(t)
    if "Level" not in c:
        continue
    key = next((k for k in ("EngineID", "DrivetrainID", "CarBodyId", "Ordinal") if k.lower() in [x.lower() for x in c]), None)
    lv = q('SELECT Level, COUNT(*) FROM "%s" GROUP BY Level ORDER BY Level' % t)
    dup = q('SELECT COUNT(*) FROM (SELECT 1 FROM "%s" GROUP BY %s, Level HAVING COUNT(*) > 1)' % (t, key))[0][0] if key else "-"
    stock = q('SELECT Level, COUNT(*) FROM "%s" WHERE IsStock=1 GROUP BY Level' % t) if "IsStock" in c else []
    print("%-38s %-10s %-34s dup=%s stock@%s" % (t, key, " ".join("%s(%s)" % x for x in lv)[:34], dup, " ".join("%s(%s)" % x for x in stock)[:30]))
print("\nCompound <-> level pairs:", q("SELECT Level, TireCompoundID, COUNT(*) FROM List_UpgradeTireCompound GROUP BY 1,2 ORDER BY 1,2"))
