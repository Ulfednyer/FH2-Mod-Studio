"""Checks everything fh3port touched: zip layout + CRCs + manifest registration, physics files, database integrity."""
import json, os, re, sqlite3, struct, subprocess, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fh3port as P


def check_zip(path):
    problems = []
    with zipfile.ZipFile(path) as z, open(path, "rb") as f:
        bad = z.testzip()
        if bad:
            problems.append("CRC error in " + bad)
        for i in z.infolist():
            f.seek(i.header_offset)
            nlen, xlen = struct.unpack_from("<HH", f.read(30), 26)
            data_off = i.header_offset + 30 + nlen + xlen
            ex = i.extra
            if len(ex) < 8 or struct.unpack_from("<H", ex, 0)[0] != 0x1123 or struct.unpack_from("<I", ex, 4)[0] != data_off:
                problems.append("no/incorrect 0x1123 field: " + i.filename)
                break
    rc, out = P.run_cli(["manifest-check", path, P.MANIFEST])
    if not all(re.search(r"%s\s+manifest=\d+\s+zip=\d+\s+OK" % k, out) for k in ("dirstart", "dirsize", "direntries")):
        problems.append("manifest: " + out.strip().splitlines()[-1][:160])
    return problems


def main():
    j = P.journal()
    zips = sorted({os.path.join(P.GAME, r) for r in list(j["backups"]) + j["created"] if r.lower().endswith(".zip")})
    bad = 0
    for z in zips:
        if not os.path.exists(z):
            print("MISSING", z); bad += 1; continue
        pr = check_zip(z)
        # FH2's own untouched entries in appended zips keep their native field, so this checks old and new entries alike
        print(("OK  " if not pr else "BAD ") + os.path.relpath(z, P.GAME), "; ".join(pr))
        bad += bool(pr)
    for r in j["created"]:
        if r.lower().endswith(".xml"):
            print(("OK  " if os.path.exists(os.path.join(P.GAME, r)) else "MISSING ") + r)
    db = sqlite3.connect("file:%s?mode=ro" % P.FH2_DB, uri=True)
    print("database:", db.execute("PRAGMA integrity_check").fetchone()[0])
    for name, info in j["cars"].items():
        if info.get("status") == "ported":
            row = db.execute("SELECT Id, DisplayName, ModelShort, BaseCost, Thumbnail FROM Data_Car WHERE Id = ?", (info["id"],)).fetchone()
            tyres = db.execute("SELECT DISTINCT TireModelName FROM List_UpgradeTireCompound WHERE Ordinal = ?", (info["id"],)).fetchall()
            susp = db.execute("SELECT DISTINCT t.Path FROM List_SpringDamperPhysics p JOIN List_SuspensionPhysicsType t ON t.SuspensionPhysicsTypeID = p.SuspensionPhysicsTypeID WHERE p.Ordinal = ?", (info["id"],)).fetchall()
            no_tyre = [t[0] for t in tyres if t[0] and not os.path.exists(os.path.join(P.TIRES2, "tire_%s.zip" % t[0]))]
            no_susp = [s[0] for s in susp if s[0] and not os.path.exists(os.path.join(P.FH2, re.sub(r"(?i)^game:\\media\\", "", s[0])))]
            print(name, row, "tyre models missing:", no_tyre, "suspension files missing:", no_susp)
    print("problems:", bad)


if __name__ == "__main__":
    main()
