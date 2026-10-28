import sqlite3, re
db = sqlite3.connect(r"file:C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt?mode=ro&immutable=1", uri=True)
cols = lambda t: [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]
sd = cols("List_SpringDamperPhysics")
print("SpringDamperPhysics:", sd)
print("Z06 L2 front:", dict(zip(sd, db.execute("SELECT * FROM List_SpringDamperPhysics WHERE SpringDamperPhysicsID=2177002").fetchone())))
print("CarBody:", cols("Data_CarBody"))
data = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\forza_durango_release_final.exe", "rb").read()
for k in (b"ModelFrontTrackOuter", b"TrackOuter", b"RimSize", b"WheelDiameter", b"TrackWidth", b"SteerRotAxisTireOffsetX"):
    print(k, [hex(m.start()) for m in re.finditer(k, data)][:6])
