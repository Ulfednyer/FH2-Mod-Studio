import sqlite3, zipfile, os
p = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\gamedbRC.slt"
d = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
rows = d.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql LIKE '%COLLATE%'").fetchall()
print("collate objects:", len(rows))
for r in rows[:12]:
    print(" ", r[0], r[1], (r[3] or "")[:160].replace("\n", " "))
print("indexes on car tables:", d.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND (tbl_name LIKE 'Data_%' OR tbl_name LIKE 'List_%')").fetchall()[:20])
print("page size / encoding / user_version / schema:", d.execute("PRAGMA page_size").fetchone(), d.execute("PRAGMA encoding").fetchone(),
      d.execute("PRAGMA user_version").fetchone(), d.execute("PRAGMA schema_version").fetchone())
print("header bytes 18-19:", open(p, "rb").read(20)[18:20], "views/triggers:", d.execute("SELECT type, COUNT(*) FROM sqlite_master GROUP BY type").fetchall())
for root in (r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\physics", r"C:\Games\Forza Horizon 3\media\physics"):
    print(root[-40:], os.listdir(root)[:15] if os.path.isdir(root) else "none")
z = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\stripped\RC6.zip"); n = [i.filename for i in z.infolist()]
print("FH3 RC6 entries", len(n), [x for x in n if "2352" in x])
z = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\RC14.zip"); n = [i.filename for i in z.infolist()]
print("FH2 RC14 entries", len(n), n[:3])
