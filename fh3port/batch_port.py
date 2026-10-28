"""Port the FH3-only cars (fh3only.json) in batches with the NSX/Centenario pipeline, check every car, roll a batch
back if a car fails and re-port it without the failing cars.

    py batch_port.py list                 batches and their cars
    py batch_port.py run <n> [size]       port batch n (1-based, default size 20)
    py batch_port.py rollback <n>         put the shared files back to the snapshot taken before batch n
    py batch_port.py cars-json            every FH3-only car with make/model/year/class and its port status (JSON)
    py batch_port.py port-cars [--keep-plates] <MediaName>...   port + check chosen cars (FH2 Mod Studio uses this)
    py batch_port.py check <MediaName>... re-run every check on installed cars
    py batch_port.py undo <snapshot>      roll back a port-cars run (its snapshot name is printed at the start)

Snapshots: FH3Port_Backup\\batches\\<n>\\ (database, zipmanifest, extended hash.manifest, Textures.zip, journal).
Report: work\\batch_<n>.md. FH2 (azimuth.exe) must be closed.
"""
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import zipfile
from datetime import datetime

import bundle
import fh3port as P
import vlayfix

RESEARCH = os.path.join(os.path.dirname(P.HERE), "research", "fh3port")
sys.path.insert(0, RESEARCH)
PY = sys.executable
SNAP_FILES = [P.FH2_DB, P.MANIFEST, P.HASH_MANIFEST, P.LIB_TEX_ZIP, P.JOURNAL]


def candidates():
    d = json.load(open(os.path.join(P.HERE, "fh3only.json")))
    return sorted((c["media"] for c in d["new"]), key=str.lower)


def known_failures():
    fl = os.path.join(P.HERE, "failed_cars.json")
    return json.load(open(fl)) if os.path.exists(fl) else {}


def batches(size, retry=False):
    """Cars still to port, in batches. Cars that failed before (failed_cars.json) are left out unless retry."""
    j = P.journal()
    failed = known_failures()
    todo = [m for m in candidates() if j["cars"].get(m, {}).get("status") != "ported" and (retry == (m in failed))]
    return [todo[i:i + size] for i in range(0, len(todo), size)]


def run(cmd, log=None):
    r = subprocess.run(cmd, cwd=P.HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    if log:
        open(log, "w", encoding="utf-8").write(out)
    return r.returncode, out


def azimuth_running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq azimuth.exe", "/NH"], capture_output=True, text=True)
    return "azimuth.exe" in r.stdout.lower()


# ───────────── snapshots ─────────────

def snap_dir(n):
    return os.path.join(P.BACKUP, "batches", str(n))


def snapshot(n):
    d = snap_dir(n)
    os.makedirs(d, exist_ok=True)
    for f in SNAP_FILES:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(d, os.path.relpath(f, P.GAME).replace(os.sep, "__")))


def rollback(n):
    d = snap_dir(n)
    old = json.load(open(os.path.join(d, os.path.relpath(P.JOURNAL, P.GAME).replace(os.sep, "__"))))
    now = P.journal()
    # files created by the batch: delete them
    for rel in set(now.get("created", [])) - set(old.get("created", [])):
        p = os.path.join(P.GAME, rel)
        if os.path.exists(p):
            os.remove(p)
    for f in SNAP_FILES:
        s = os.path.join(d, os.path.relpath(f, P.GAME).replace(os.sep, "__"))
        if os.path.exists(s):
            shutil.copy2(s, f)
    # files the batch backed up for the first time (overwritten car zips of replaced cars) - none for new cars
    for rel in set(now.get("backups", {})) - set(old.get("backups", {})):
        src = os.path.join(P.BACKUP, "files", rel)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(P.GAME, rel))


# ───────────── checks ─────────────

def verify_all(n):
    """verify.py checks every touched zip, the physics files and the database in one go (it ignores car names),
    so it runs once per round. Returns {zip path (lower): problem} and a list of non-zip problems."""
    rc, out = run([PY, "-I", "verify.py"], os.path.join(P.WORK, "batch_%s_verify.log" % n))
    bad_zips, other = {}, []
    for line in out.splitlines():
        if line.startswith("BAD ") or line.startswith("MISSING"):
            path = line.split(None, 1)[1].split(" ", 1)[0] if " " in line else line
            bad_zips[os.path.normpath(os.path.join(P.GAME, path)).lower()] = line.strip()
        elif line.startswith("database:") and not line.strip().endswith("ok"):
            other.append(line.strip())
    if "problems:" not in out:
        other.append("verify.py did not finish (see work\\batch_%s_verify.log)" % n)
    return bad_zips, other


def check_car(media, bad_zips, db):
    import superset
    problems = []
    zp = os.path.join(P.FH2, "cars", media + ".zip")
    if not os.path.exists(zp):
        return ["car zip missing"]
    if os.path.normpath(zp).lower() in bad_zips:
        problems.append("verify: " + bad_zips[os.path.normpath(zp).lower()])
    row = db.execute("SELECT Id FROM Data_Car WHERE MediaName = ? COLLATE NOCASE", (media,)).fetchone()
    if not row:
        problems.append("no Data_Car row")
    elif not db.execute("SELECT 1 FROM List_UpgradeEngine WHERE Ordinal = ?", (row[0],)).fetchone():
        problems.append("no engine rows")
    for script, ok in (("strict.py", "mismatches 0"), ("modlcounts.py", "mismatches 0")):
        rc, out = run([PY, "-I", os.path.join(RESEARCH, script), zp])
        last = out.strip().splitlines()[-1] if out.strip() else "no output"
        if ok not in last:
            problems.append("%s: %s" % (script, last[-80:]))
    import physdef
    need, ok = physdef.check_zip(zp)
    if not ok:
        problems.append("physicsdefinition.bin would crash FH2 (collision %s bytes, limit %d, or child model table set); re-port" % (need, physdef.LIMIT))
    rc, out = run([PY, "-I", "carbin.py", "check", zp])
    if "failed: 0" not in out:
        problems.append("carbin check failed")
    import collections
    c = collections.Counter()
    superset.scan(zp, media, c, [])
    if c.get("MISSING inputs"):
        problems.append("%d meshes miss shader inputs" % c["MISSING inputs"])
    sizes = order = 0
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            d = z.read(n)
            if d[:4] != b"burG" or d[4:6] != b"\x01\x00":
                continue
            for i in range(struct.unpack_from("<H", d, 6)[0]):
                size, usize = struct.unpack_from("<II", d, 16 + 24 * i + 16)
                sizes += size != usize
            if n.lower().endswith(".modelbin"):
                ids = [vlayfix._id(b) for b in bundle.parse(d) if b.tag == b"yaLV"]
                order += not all(v == i or (v == -1 and i == len(ids) - 1) for i, v in enumerate(ids))
    if sizes:
        problems.append("%d blobs with size != usize" % sizes)
    if order:
        problems.append("%d models break the layout order" % order)
    return problems


def _check_job(args):
    """check_car in a worker process (its own read-only database connection)."""
    media, bad_zips = args
    db = sqlite3.connect("file:" + P.FH2_DB + "?mode=ro", uri=True)
    try:
        return check_car(media, bad_zips, db)
    finally:
        db.close()


def check_cars_parallel(cars, bad_zips):
    """{car: problems} - the checks start 3 Python processes and read the whole zip per car; one car after another
    they took ~4 of the 18 minutes of a 287-car run, so they run side by side like the conversions."""
    workers = min(P.CONVERT_WORKERS, len(cars))
    if workers <= 1:
        return {m: _check_job((m, bad_zips)) for m in cars}
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(workers) as ex:
        return dict(zip(cars, ex.map(_check_job, [(m, bad_zips) for m in cars])))


def donors(cars):
    """Engine-sound source per car, read from the database: the MediaName of each of its engines."""
    db = sqlite3.connect("file:" + P.FH2_DB + "?mode=ro", uri=True)
    out = {}
    for m in cars:
        row = db.execute("SELECT Id FROM Data_Car WHERE MediaName = ? COLLATE NOCASE", (m,)).fetchone()
        if row:
            stock = db.execute("SELECT DE.MediaName FROM List_UpgradeEngine LU JOIN Data_Engine DE ON DE.EngineID = LU.EngineID "
                               "WHERE LU.Ordinal = ? AND LU.IsStock = 1", (row[0],)).fetchone()
            out[m] = stock[0] if stock else ""
    db.close()
    return out


def port_batch(n, cars, keep_plates=False):
    """fh3port.py port, its output echoed line by line as it comes (FH2 Mod Studio shows it live) and logged."""
    log = os.path.join(P.WORK, "batch_%s_port.log" % n)
    cmd = [PY, "-u", "fh3port.py", "port"] + cars + (["--keep-plates"] if keep_plates else [])
    proc = subprocess.Popen(cmd, cwd=P.HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    lines = []
    for line in proc.stdout:
        lines.append(line)
        print("   | " + line.rstrip()[:300], flush=True)
    proc.wait()
    out = "".join(lines)
    open(log, "w", encoding="utf-8").write(out)
    return proc.returncode, out


def run_batch(n, size):
    if azimuth_running():
        sys.exit("Forza Horizon 2 (azimuth.exe) is running - close it first.")
    bs = batches(size)
    if not bs:
        sys.exit("nothing left to port")
    # batches() lists only what is still to do, so the batch to run is always the first one; n names the
    # snapshot and the report (run batches in order: 1, 2, 3 ...)
    port_cars(n, bs[0])


def port_cars(n, cars, keep_plates=False):
    """Ports cars, checks each, rolls the run back and re-ports without the cars that failed (up to 3 rounds).
    n names the snapshot and the report. Returns (ok cars, {failed car: reason})."""
    os.makedirs(P.WORK, exist_ok=True)
    started = datetime.now()
    snapshot(n)
    failed = {}
    attempt = list(cars)
    for round_ in range(3):
        print("== batch %s round %d: %d cars" % (n, round_ + 1, len(attempt)), flush=True)
        rc, out = port_batch(n, attempt, keep_plates)
        j = P.journal()
        if "database written" not in out:
            # the port run itself died (nothing was written): every car of the round counts as failed
            tail = out.strip().splitlines()[-1] if out.strip() else "no output"
            print("   port run aborted: " + tail, flush=True)
        conv_failed = [m for m in attempt if j["cars"].get(m, {}).get("status") != "ported"]
        for m in conv_failed:
            info = j["cars"].get(m, {})
            failed[m] = "%s: %s" % (info.get("status", "not ported"), info.get("reason", "see work\\batch_%s_port.log" % n))
        bad = {}
        bad_zips, other = verify_all(n)
        checked = check_cars_parallel([m for m in attempt if m not in conv_failed], bad_zips)
        for m, p in checked.items():
            print("   %-32s %s" % (m, "ok" if not p else "; ".join(p)), flush=True)
            if p:
                bad[m] = "; ".join(p)
        db = sqlite3.connect("file:" + P.FH2_DB + "?mode=ro", uri=True)
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        db.close()
        car_zips = {os.path.normpath(os.path.join(P.FH2, "cars", m + ".zip")).lower() for m in attempt}
        shared_bad = [v for k, v in bad_zips.items() if k not in car_zips]
        if integrity != "ok" or other or shared_bad:
            bad["(database)"] = "; ".join((["integrity check: " + integrity] if integrity != "ok" else []) + other + shared_bad)
        if not bad and not conv_failed:
            break
        failed.update({k: v for k, v in bad.items() if k != "(database)"})
        print("   rolling back batch %s, re-porting without %d failed cars" % (n, len(bad) + len(conv_failed)), flush=True)
        rollback(n)
        attempt = [m for m in attempt if m not in failed]
        if not attempt or "(database)" in bad:
            break
    j = P.journal()
    ok = [m for m in cars if j["cars"].get(m, {}).get("status") == "ported" and m not in failed]
    don = donors(ok)
    lines = ["# Batch %s (%s, %s)" % (n, started.strftime("%Y-%m-%d %H:%M"), str(datetime.now() - started).split(".")[0]), "",
             "Ported and checked: %d of %d. Failed (rolled back, listed for later): %d." % (len(ok), len(cars), len(failed)), "",
             "| Car | Result | Engine sound (FH2 engine name) |", "|---|---|---|"]
    for m in cars:
        sound = don.get(m, "")
        lines.append("| `%s` | %s | %s |" % (m, "ok" if m in ok else "FAILED: " + failed.get(m, "not ported").replace("|", "/"),
                                            ("own" if sound.lower() == m.lower() else sound) if m in ok else ""))
    # failures are kept in a file so later batches/fixes can retry them
    fl = os.path.join(P.HERE, "failed_cars.json")
    allf = json.load(open(fl)) if os.path.exists(fl) else {}
    allf.update(failed)
    for m in ok:
        allf.pop(m, None)
    json.dump(allf, open(fl, "w"), indent=1)
    rep = os.path.join(P.WORK, "batch_%s.md" % n)
    open(rep, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("report:", rep)
    write_ported_list()
    print("full list of ported cars:", os.path.join(P.HERE, "PORTED_CARS.md"))
    return ok, failed


def write_ported_list():
    """PORTED_CARS.md: every car installed by the porter (from the journal), with name, class and engine sound."""
    j = P.journal()
    info = {c["media"]: c for c in json.load(open(os.path.join(P.HERE, "fh3only.json")))["new"]}
    cars = sorted((m for m, v in j["cars"].items() if v.get("status") == "ported"), key=lambda m: j["cars"][m].get("at", ""))
    if any(m not in info for m in cars):
        # cars that replaced FH2's version are not in fh3only.json: names from FH3's database and string table
        from fh3only import CLASSES
        db3 = P.open_ro(P.FH3_DB)
        makes = {r[0]: r[1] for r in db3.execute("SELECT ID, DisplayName FROM List_CarMake")}
        st = P.Fh3Strings()
        for car in P.fh3_cars().values():
            m = car["MediaName"]
            if m in cars and m not in info:
                info[m] = {"make": st.text("List_CarMake", makes.get(car["MakeID"], "")) or "",
                           "model": st.text("Data_Car", car["DisplayName"]) or m, "year": car["Year"],
                           "class": CLASSES.get(car["ClassID"], str(car["ClassID"]))}
        info.update({k: info[k2] for k2 in list(info) for k in cars if k.lower() == k2.lower() and k not in info})
    don = donors(cars)
    lines = ["# Cars ported from FH3 to FH2", "", "%d cars installed (updated %s). In the Autoshow under their make." % (
        len(cars), datetime.now().strftime("%Y-%m-%d %H:%M")), "",
             "| # | Car | Year | Class | MediaName | Engine sound | Ported |", "|---|---|---|---|---|---|---|"]
    for i, m in enumerate(cars, 1):
        c = info.get(m, {})
        s = don.get(m, "")
        lines.append("| %d | %s %s | %s | %s | `%s` | %s | %s |" % (
            i, c.get("make", ""), c.get("model", m), c.get("year", ""), c.get("class", ""), m,
            "own FH2 sound" if s.lower() == m.lower() else "borrowed: " + s, j["cars"][m].get("at", "")[:16].replace("T", " ")))
    fl = known_failures()
    if fl:
        lines += ["", "## Not ported yet (failed, to fix later)", "", "| Car | MediaName | Reason |", "|---|---|---|"]
        for m, r in sorted(fl.items()):
            c = info.get(m, {})
            lines.append("| %s %s | `%s` | %s |" % (c.get("make", ""), c.get("model", m), m, r.replace("|", "/")))
    open(os.path.join(P.HERE, "PORTED_CARS.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return lines


def cars_json():
    """Every FH3-only car (fh3only.json) with its status: ported / failed (reason) / new."""
    import fh3only
    fh3only.ensure()
    j = P.journal()
    failed = known_failures()
    out = []
    for c in json.load(open(os.path.join(P.HERE, "fh3only.json")))["new"]:
        m = c["media"]
        st = j["cars"].get(m, {})
        status = "ported" if st.get("status") == "ported" else \
            "failed" if m in failed or st.get("status", "").endswith("failed") else "new"
        out.append({"media": m, "make": c.get("make", ""), "model": c.get("model", ""), "year": c.get("year", ""),
                    "class": c.get("class", ""), "autoshow": c.get("autoshow", True), "status": status,
                    "reason": failed.get(m) or st.get("reason", ""), "ported_at": st.get("at", "")})
    # FH3 cars FH2 has too: porting one replaces FH2's version (FH3 bodykits / widebody parts FH2 lacks); FH2's
    # files and rows are backed up first, so undo / restore bring the original back
    from fh3only import CLASSES
    have = {c["media"].lower() for c in out}
    c3 = P.fh3_cars()
    db3 = P.open_ro(P.FH3_DB)
    makes = {r[0]: r[1] for r in db3.execute("SELECT ID, DisplayName FROM List_CarMake")}
    strings = P.Fh3Strings()
    for f, action, why in P.plan():
        media = os.path.splitext(f)[0]
        if action != "replace" or media.lower() in have:
            continue
        car = c3[media.lower()]
        st = j["cars"].get(car["MediaName"], {})
        status = "ported" if st.get("status") == "ported" else \
            "failed" if car["MediaName"] in failed or st.get("status", "").endswith("failed") else "in_fh2"
        out.append({"media": car["MediaName"], "make": strings.text("List_CarMake", makes.get(car["MakeID"], "")) or "",
                    "model": strings.text("Data_Car", car["DisplayName"]) or car["MediaName"], "year": car["Year"],
                    "class": CLASSES.get(car["ClassID"], str(car["ClassID"])), "autoshow": True, "status": status,
                    "reason": failed.get(car["MediaName"]) or st.get("reason", ""), "ported_at": st.get("at", ""),
                    "replaces": why})
    return out


def check_cars(cars):
    """Every check on installed cars: verify.py, the per-car model checks and the database read-back (dbcheck)."""
    import dbcheck
    bad_zips, other = verify_all("check")
    db = sqlite3.connect("file:" + P.FH2_DB + "?mode=ro", uri=True)
    porter = P.Porter(P.journal(), P.FH2_DB)
    res = {}
    model_checks = check_cars_parallel(list(cars), bad_zips)
    for m in cars:
        p = list(model_checks[m])
        row = db.execute("SELECT Id FROM Data_Car WHERE MediaName = ? COLLATE NOCASE", (m,)).fetchone()
        if row:
            v = dbcheck.Validator(porter)
            for t, c in porter.car_tables.items():
                if c in porter.cols2[t]:
                    cc = [r[1] for r in porter.fh2.execute('PRAGMA table_info("%s")' % t)]
                    rows = porter.fh2.execute('SELECT * FROM "%s" WHERE "%s" = ?' % (t, c), (row[0],)).fetchall()
                    if rows:
                        v.inserted.append((t, cc, [list(r) for r in rows], True))
            errors, _ = v.after(row[0])
            p += ["database: " + e for e in errors]
        res[m] = p
        print("CHECK %s %s" % (m, "OK" if not p else "FAIL " + "; ".join(p)), flush=True)
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    db.close()
    if integrity != "ok" or other:
        print("CHECK (database) FAIL " + "; ".join(([integrity] if integrity != "ok" else []) + other), flush=True)
    return res


def main():
    a = sys.argv[1:]
    if not a or a[0] == "list":
        for i, b in enumerate(batches(int(a[1]) if len(a) > 1 else 20), 1):
            print("batch %d (%d): %s" % (i, len(b), " ".join(b)))
    elif a[0] == "run":
        run_batch(int(a[1]), int(a[2]) if len(a) > 2 else 20)
    elif a[0] == "rollback":
        if azimuth_running():
            sys.exit("close FH2 first")
        rollback(int(a[1]))
        print("rolled back to the snapshot before batch", a[1])
    elif a[0] == "cars-json":
        print(json.dumps(cars_json()))
    elif a[0] == "port-cars":
        if azimuth_running():
            print("RESULT " + json.dumps({"error": "Forza Horizon 2 (azimuth.exe) is running - close it first."}))
            sys.exit(2)
        cars = P.use_zips([x for x in a[1:] if not x.startswith("--")])     # zip paths -> media names
        tag = "ui-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        print("SNAPSHOT " + tag, flush=True)
        ok, failed = port_cars(tag, cars, keep_plates="--keep-plates" in a)
        print("RESULT " + json.dumps({"snapshot": tag, "ok": ok, "failed": failed}), flush=True)
    elif a[0] == "check":
        check_cars(a[1:])
    elif a[0] == "undo":
        if azimuth_running():
            sys.exit("close FH2 first")
        rollback(a[1])
        write_ported_list()
        print("UNDONE " + a[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
