import sqlite3, zipfile, re
def open_(p):
    db = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return db
fh2 = open_(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt")
fh3 = open_(r"C:\Games\Forza Horizon 3\media\stripped\gamedbRC.slt")
cols = lambda db, t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
tabs = sorted(r[0] for r in fh2.execute("SELECT name FROM sqlite_master WHERE type='table'"))
print("FH2 autoshow/shop-ish tables:", [t for t in tabs if re.search("auto|show|dealer|shop|buy|catalog|unlock|reward|garage|gift", t, re.I)])
print("FH2 Data_Car cols:", cols(fh2, "Data_Car"))
nsx = fh3.execute("SELECT * FROM Data_Car WHERE MediaName='ACU_NSX_16'").fetchone()
print("FH3 NSX:", dict(zip(cols(fh3, "Data_Car"), nsx)))
# every FH2 table that has a column naming a car (CarId / Ordinal / CarID) -> where cars are referenced
ref = {}
for t in tabs:
    for c in cols(fh2, t):
        if c.lower() in ("carid", "ordinal", "car", "carordinal", "car_id"):
            ref.setdefault(t, []).append(c)
print("FH2 tables keyed by car:", ref)
z = fh2.execute("SELECT * FROM Data_Car WHERE Id=2177").fetchone()
print("FH2 Z06 row:", dict(zip(cols(fh2, "Data_Car"), z)))
for zp in (r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\stringtables\EN.zip",):
    zz = zipfile.ZipFile(zp)
    print("EN.zip entries:", [(i.filename, i.file_size) for i in zz.infolist()][:20])
