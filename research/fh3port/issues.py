import sqlite3, os
def o(p):
    d = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    d.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return d
orig = o(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\FH3Port_Backup\files\Mount\media\stripped\gamedbRC.slt")
cur = o(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt")
f3 = o(r"C:\Games\Forza Horizon 3\media\stripped\gamedbRC.slt")
print("FH2 original engine 2292:", orig.execute("SELECT EngineID, MediaName FROM Data_Engine WHERE EngineID=2292").fetchone(),
      "used by", orig.execute("SELECT Ordinal FROM List_UpgradeEngine WHERE EngineID=2292").fetchall())
e2 = {r[0]: (r[1] or "").lower() for r in orig.execute("SELECT EngineID, MediaName FROM Data_Engine")}
e3 = {r[0]: (r[1] or "").lower() for r in f3.execute("SELECT EngineID, MediaName FROM Data_Engine")}
clash = [(i, e2[i], e3[i]) for i in e3 if i in e2 and e2[i] != e3[i]]
print("engine id clashes (different MediaName):", len(clash), clash[:10])
# drivetrains / bodies: no media name; compare by owning car
def owners(db, t, k):
    m = {}
    for i, o_ in db.execute("SELECT %s, Ordinal FROM %s WHERE IsStock=1" % (k, t)):
        m.setdefault(i, set()).add(o_)
    return m
for t, k in (("List_UpgradeDrivetrain", "DrivetrainID"), ("List_UpgradeCarBody", "CarBodyID")):
    a, b = owners(orig, t, k), owners(f3, t, k)
    n2 = {r[0]: r[1].lower() for r in orig.execute("SELECT Id, MediaName FROM Data_Car")}
    n3 = {r[0]: r[1].lower() for r in f3.execute("SELECT Id, MediaName FROM Data_Car")}
    bad = [(i, [n2.get(x) for x in a[i]], [n3.get(x) for x in b[i]]) for i in b if i in a and {n2.get(x) for x in a[i]}.isdisjoint({n3.get(x) for x in b[i]})]
    print(t, "id clashes (stock owner differs):", len(bad), bad[:6])
print("susp types in FH2 now:", cur.execute("SELECT SuspensionPhysicsTypeID FROM List_SuspensionPhysicsType WHERE SuspensionPhysicsTypeID > 19").fetchall())
print("susp type cols:", [c[1] for c in cur.execute("PRAGMA table_info(List_SuspensionPhysicsType)")])
sus2 = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\physics\suspension"
print("FH2 suspension files:", sorted(os.listdir(sus2)))
print("FH3 suspension files:", sorted(os.listdir(r"C:\Games\Forza Horizon 3\media\physics\suspension")))
for root in (r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\scene\tires", r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires"):
    print(root[-50:], sorted(os.listdir(root)))
print("FH3 tire model names:", f3.execute("SELECT TireModelName, COUNT(*) FROM List_UpgradeTireCompound GROUP BY 1 ORDER BY 2 DESC").fetchall())
