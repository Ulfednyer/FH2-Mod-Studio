"""List the FH3 cars FH2 doesn't have (compared with the ORIGINAL FH2 database in the backup, so cars already
ported still count), with name, class, PI, drivable/autoshow flags and zip size; also the FH3 zips that can't be
ported and why. Writes FH3_ONLY_CARS.md and fh3only.json.  usage: py fh3only.py"""
import json
import os
import sqlite3

import fh3port as P

ORIG_DB = os.path.join(P.BACKUP, "files", "Mount", "media", "stripped", "gamedbRC.slt")
CLASSES = {0: "D", 1: "C", 2: "B", 3: "A", 4: "S1", 5: "S2", 6: "X", 7: "X"}   # FH3 CarClasses 6 = CLASS_R, 7 = CLASS_X


def source_key():
    """What the list was built from: the FH3 media folders and their database / car folder dates."""
    import fh3lib
    stamp = [os.path.getmtime(p) for p in [P.FH3_DB] + fh3lib.find_all("cars") if os.path.exists(p)]
    return {"roots": fh3lib.ROOTS, "db": P.FH3_DB, "stamp": max(stamp) if stamp else 0}


def ensure():
    """Rebuild fh3only.json when the media folders, the FH3 database or a car folder changed."""
    try:
        if json.load(open(os.path.join(P.HERE, "fh3only.json"))).get("source") == source_key():
            return
    except (OSError, ValueError):
        pass
    main()


def main():
    db2 = P.open_ro(ORIG_DB if os.path.exists(ORIG_DB) else P.FH2_DB)
    names2 = {r[0].lower(): r[1] for r in db2.execute("SELECT MediaName, Id FROM Data_Car")}
    ids2 = {r[1]: r[0] for r in db2.execute("SELECT MediaName, Id FROM Data_Car")}
    db3 = P.open_ro(P.FH3_DB)
    c3 = [r[1] for r in db3.execute("PRAGMA table_info(Data_Car)")]
    cars3 = {r[c3.index("MediaName")].lower(): dict(zip(c3, r)) for r in db3.execute("SELECT * FROM Data_Car")}
    makes = {r[0]: r[1] for r in db3.execute("SELECT ID, DisplayName FROM List_CarMake")}
    st = P.Fh3Strings()
    j = P.journal()
    paths = P.fh3_car_zips()                    # every FH3 media folder (fh3port.ini fh3 + fh3_extra)
    zips = {k: os.path.basename(v) for k, v in paths.items()}
    new, skipped = [], []
    for key, f in sorted(zips.items()):
        car = cars3.get(key)
        size = os.path.getsize(paths[key]) // 2 ** 20
        if not car:
            skipped.append((f, "no FH3 database row (DLC/pack or shared file)", size))
            continue
        if key in names2:
            continue                       # FH2 has this car
        if car["Id"] in ids2:
            skipped.append((f, "FH3 id %d already belongs to FH2's %s" % (car["Id"], ids2[car["Id"]]), size))
            continue
        make = st.text("List_CarMake", makes.get(car["MakeID"], "")) or ""
        model = st.text("Data_Car", car["DisplayName"]) or car["MediaName"]
        new.append({"media": car["MediaName"], "id": car["Id"], "make": make, "model": model, "year": car["Year"],
                    "class": CLASSES.get(car["ClassID"], str(car["ClassID"])), "pi": car["PerformanceIndex"],
                    "drivable": bool(car.get("IsDrivable", 1)), "autoshow": not car.get("NotAvailableInAutoshow"),
                    "zip_mb": size, "status": j["cars"].get(car["MediaName"], {}).get("status", "")})
    json.dump({"new": new, "skipped": skipped, "source": source_key()}, open(os.path.join(P.HERE, "fh3only.json"), "w"), indent=1)
    lines = ["# FH3 cars that Forza Horizon 2 doesn't have", "",
             "Compared with the original FH2 database. %d cars can be added; %d FH3 zips can't (see the end)." % (len(new), len(skipped)),
             "Status: `ported` = already installed.", "",
             "| # | MediaName | Car | Year | Class | PI | Drivable | Autoshow | Zip MB | Status |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(sorted(new, key=lambda c: (c["make"], c["year"], c["model"])), 1):
        lines.append("| %d | `%s` | %s %s | %s | %s | %s | %s | %s | %d | %s |" % (
            i, c["media"], c["make"], c["model"], c["year"], c["class"], c["pi"], "yes" if c["drivable"] else "no",
            "yes" if c["autoshow"] else "no", c["zip_mb"], c["status"]))
    lines += ["", "## FH3 zips that can't be added", "", "| Zip | Reason | MB |", "|---|---|---|"]
    lines += ["| `%s` | %s | %d |" % s for s in skipped]
    open(os.path.join(P.HERE, "FH3_ONLY_CARS.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("new %d, skipped %d, already ported %d, not drivable %d, not in autoshow %d, total zip MB %d" % (
        len(new), len(skipped), sum(c["status"] == "ported" for c in new), sum(not c["drivable"] for c in new),
        sum(not c["autoshow"] for c in new), sum(c["zip_mb"] for c in new)))


if __name__ == "__main__":
    main()
