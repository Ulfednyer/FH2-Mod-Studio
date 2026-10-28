import sqlite3, zipfile, os
def open_(p):
    db = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return db
FH2 = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
FH3 = r"C:\Games\Forza Horizon 3\media"
fh2 = open_(FH2 + r"\stripped\gamedbRC.slt"); fh3 = open_(FH3 + r"\stripped\gamedbRC.slt")
cols = lambda db, t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
# lookup tables referenced by Data_Car / engine columns: compare common ids
for t in ("List_CarMake", "List_Country", "List_Region", "List_CarType", "List_Cylinders", "List_EngineConfig", "List_EnginePlacement",
          "List_DriveType", "List_Aspiration", "List_MaterialType", "List_TireBrand", "List_TireCompound", "Powertrains", "List_BrakeType",
          "List_CarClass", "List_FamilyModel", "List_FamilyBody", "List_FamilySpecial", "List_SuspensionPhysicsType", "List_AutoSteerOverrides", "AutoSteerOverrides"):
    try:
        c2, c3 = cols(fh2, t), cols(fh3, t)
    except Exception as e:
        continue
    if not c2 or not c3:
        print(t, "missing in", "FH2" if not c2 else "FH3"); continue
    k = c2[0]
    common = [c for c in c2 if c in c3]
    r2 = {r[0]: r for r in fh2.execute('SELECT %s FROM "%s"' % (",".join('"%s"' % c for c in common), t))}
    r3 = {r[0]: r for r in fh3.execute('SELECT %s FROM "%s"' % (",".join('"%s"' % c for c in common), t))}
    same = sum(1 for i in r3 if i in r2 and r2[i] == r3[i])
    diffs = [(i, r2[i][:4], r3[i][:4]) for i in r3 if i in r2 and r2[i] != r3[i]][:3]
    print("%-28s FH2 %3d FH3 %3d same %3d differ %3d FH3-only %3d  %s" % (t, len(r2), len(r3), same, sum(1 for i in r3 if i in r2) - same, sum(1 for i in r3 if i not in r2), diffs))
print([r[0] for r in fh2.execute("SELECT name FROM sqlite_master WHERE name LIKE 'List_Car%' OR name LIKE '%Make%'")])
st3 = FH3 + r"\stripped\stringtables"
print("FH3 stringtables:", os.listdir(st3)[:20])
