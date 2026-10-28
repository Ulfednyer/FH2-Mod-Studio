import sqlite3, zipfile, os
def o(p):
    d = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    d.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return d
f2 = o(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt")
f3 = o(r"C:\Games\Forza Horizon 3\media\stripped\gamedbRC.slt")
cols = lambda d, t: [r[1] for r in d.execute('PRAGMA table_info("%s")' % t)]
for d, lab in ((f3, "FH3"), (f2, "FH2")):
    for t in [r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        cs = cols(d, t)
        if "torque" in t.lower() or any("torquecurve" in c.lower() for c in cs[:2]) or "manufacturer" in t.lower():
            print(lab, t, cs[:6], d.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone())
print("NSX cam curve ids:", f3.execute("SELECT EngineID, Level, TorqueCurveFullThrottleID FROM List_UpgradeEngineCamshaft WHERE EngineID IN (2482, 2292)").fetchall())
print("FH2 Z06 cam curve ids:", f2.execute("SELECT EngineID, Level, TorqueCurveFullThrottleID FROM List_UpgradeEngineCamshaft WHERE EngineID = 2305").fetchall())
# where are the AO textures in FH3?
needle = "acu_caliperlf_003"
for root, _, fs in os.walk(r"C:\Games\Forza Horizon 3\media\cars"):
    for f in fs:
        if f.lower().endswith(".zip") and ("_library" in root.lower() or f.lower().startswith("acu_nsx")):
            try:
                z = zipfile.ZipFile(os.path.join(root, f))
            except Exception:
                continue
            hits = [n for n in z.namelist() if needle in n.lower() or "plate_ao" in n.lower()]
            if hits:
                print("AO in", os.path.join(root, f), hits[:4])
