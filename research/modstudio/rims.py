import sqlite3
db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
q = lambda s: db.execute(s).fetchall()
cols = lambda t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
for t in ("List_UpgradeRimSizeFront", "List_UpgradeRimSizeRear", "List_Wheels", "CarTrackOffsets"):
    print(t, cols(t))
print("Z06 rims F:", q("SELECT * FROM List_UpgradeRimSizeFront WHERE Ordinal=2177"))
print("Z06 rims R:", q("SELECT * FROM List_UpgradeRimSizeRear WHERE Ordinal=2177"))
print("rim sample:", q("SELECT * FROM List_UpgradeRimSizeFront WHERE Ordinal=(SELECT Ordinal FROM List_UpgradeRimSizeFront GROUP BY Ordinal HAVING COUNT(*)>=5 LIMIT 1)"))
print("rim dup example:", q("SELECT Ordinal, Level, COUNT(*) FROM List_UpgradeRimSizeFront GROUP BY 1,2 HAVING COUNT(*)>1"))
# columns containing offset/track/width anywhere
for (n,) in q("SELECT name FROM sqlite_master WHERE type='table'"):
    hits = [c for c in cols(n) if any(k in c.lower() for k in ("offset", "track", "spacer", "rimwidth", "wheelwidth", "scrub"))]
    if hits: print("COL", n, hits)
print("Data_Car track cols:", [c for c in cols("Data_Car") if "track" in c.lower() or "width" in c.lower() or "wheel" in c.lower()])
print("TrackOffsets vs rim count:", q("SELECT COUNT(*), SUM(Id IN (SELECT Ordinal FROM List_UpgradeRimSizeFront WHERE Level>0)) FROM CarTrackOffsets"))
print("Upgrade offset nonzero:", q("SELECT COUNT(*), SUM(UpgradeFrontOffset<>0 OR UpgradeRearOffset<>0), SUM(FrontOffset<>0 OR RearOffset<>0) FROM CarTrackOffsets"))
