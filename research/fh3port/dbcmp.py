import sqlite3
def open_(p):
    db = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return db
fh2 = open_(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt")
fh3 = open_(r"C:\Games\Forza Horizon 3\media\stripped\gamedbRC.slt")
tabs = lambda db: {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
cols = lambda db, t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
t2, t3 = tabs(fh2), tabs(fh3)
print("tables FH2 %d FH3 %d common %d" % (len(t2), len(t3), len(t2 & t3)))
print("sqlite FH3 header:", open(r"C:\Games\Forza Horizon 3\media\stripped\gamedbRC.slt", "rb").read(16))
car_tables = sorted(t for t in t2 & t3 if t.startswith(("Data_Car", "Data_Engine", "Data_Drivetrain", "Data_CarBody", "List_Upgrade", "List_Wheels", "List_SpringDamperPhysics", "List_AntiSwayPhysics", "List_TireCompound", "CarTrackOffsets", "Powertrains")))
diff = 0
for t in car_tables:
    c2, c3 = cols(fh2, t), cols(fh3, t)
    if c2 != c3:
        diff += 1
        print("%-40s FH2-only %s | FH3-only %s" % (t, sorted(set(c2) - set(c3))[:8], sorted(set(c3) - set(c2))[:8]))
print("car tables compared %d, differing %d" % (len(car_tables), diff))
print("FH2-only car-ish tables:", sorted(t for t in t2 - t3 if "Car" in t or "Upgrade" in t)[:30])
print("FH3-only car-ish tables:", sorted(t for t in t3 - t2 if "Car" in t or "Upgrade" in t)[:40])
n2 = {r[0]: r[1] for r in fh2.execute("SELECT Id, MediaName FROM Data_Car")}
n3 = {r[0]: r[1] for r in fh3.execute("SELECT Id, MediaName FROM Data_Car")}
print("Data_Car rows FH2 %d FH3 %d" % (len(n2), len(n3)))
same = [i for i in n3 if i in n2]
clash = [(i, n2[i], n3[i]) for i in same if (n2[i] or "").lower() != (n3[i] or "").lower()]
print("FH3 Ids also in FH2: %d, of which different car: %d e.g. %s" % (len(same), len(clash), clash[:6]))
m2 = {(v or "").lower() for v in n2.values()}
print("FH3 cars by name not in FH2:", sum(1 for v in n3.values() if (v or "").lower() not in m2))
