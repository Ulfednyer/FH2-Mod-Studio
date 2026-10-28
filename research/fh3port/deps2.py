import sqlite3, os, re
def open_(p):
    db = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return db
FH2 = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
FH3 = r"C:\Games\Forza Horizon 3\media"
fh2 = open_(FH2 + r"\stripped\gamedbRC.slt"); fh3 = open_(FH3 + r"\stripped\gamedbRC.slt")
cols = lambda db, t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
q = lambda db, s: db.execute(s).fetchall()
print("FH3 wheel 12623:", q(fh3, "SELECT * FROM List_Wheels WHERE ID=12623"))
print("FH2 has wheel 12623:", q(fh2, "SELECT ID, MediaName FROM List_Wheels WHERE ID=12623"))
print("FH2 Z06 wheel:", q(fh2, "SELECT ID, MediaName, Type FROM List_Wheels WHERE ID=12465"))
for root in (FH2, FH3):
    for sub in (r"cars\_library\scene\wheels", r"brakes", r"audio", r"audio\cars", r"cars\_library\scene"):
        p = os.path.join(root, sub)
        if os.path.isdir(p):
            items = os.listdir(p)
            print(root[-30:], sub, len(items), [i for i in items if re.search("nsx|corvettez06|acu_", i, re.I)][:6], items[:5])
print("FH3 eng for NSX:", q(fh3, "SELECT EngineID, Level, IsStock FROM List_UpgradeEngine WHERE Ordinal=2352"))
eng_cols = cols(fh3, "Data_Engine"); print("Data_Engine cols:", eng_cols)
print("price-ish FH3 tables:", [r[0] for r in fh3.execute("SELECT name FROM sqlite_master WHERE type='table'") if re.search("price|cost|value|autoshow|showroom", r[0], re.I)])
print("FH2 IEAutoShowCars:", cols(fh2, "IEAutoShowCars"), q(fh2, "SELECT COUNT(*) FROM IEAutoShowCars"), q(fh2, "SELECT * FROM IEAutoShowCars LIMIT 3"))
print("FH2 IsPurchased/ContentId:", q(fh2, "SELECT IsPurchased, ContentId, IsInstalled, IsDrivable, COUNT(*) FROM Data_Car GROUP BY 1,2,3,4"))
print("FH3 BaseCost distribution:", q(fh3, "SELECT MIN(BaseCost), MAX(BaseCost), SUM(BaseCost<=1), COUNT(*) FROM Data_Car"))
print("FH2 BaseCost distribution:", q(fh2, "SELECT MIN(BaseCost), MAX(BaseCost), SUM(BaseCost<=1), COUNT(*) FROM Data_Car"))
print("FH3 Id range:", q(fh3, "SELECT MIN(Id), MAX(Id) FROM Data_Car"), "FH2:", q(fh2, "SELECT MIN(Id), MAX(Id) FROM Data_Car"))
