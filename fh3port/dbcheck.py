"""Database validation for ported cars: every row is checked before it goes into FH2's database and read back after.

Before (Porter.insert -> Validator.before): the FH3 rows against FH2's schema and data
  - FH3 columns FH2 doesn't have that carry data (dropped: GearRatio9/10 of a 10-speed, ...)       warning
  - a value whose type doesn't fit FH2's column (text in an INTEGER column)                         error
  - a value of a small enumeration FH2 never uses in that column (ClassID, CarTypeID, ...)          warning
After (Validator.after, once the car's rows are in, inside its savepoint):
  - every inserted row is read back; columns must hold exactly what was inserted, except the ones the porter
    rewrites on purpose afterwards (ALLOWED) - those are checked for their own rules instead           error
  - every reference column of an inserted row points at an existing FH2 row (or is 0/-1/empty)        error
  - Data_Car: MakeID exists, MakeName = that make's DisplayName, names are text (no unresolved _& ids),
    price > 1, bucket is one FH2 uses, every engine's MediaName has an FH2 sound bank                   error

Errors fail the car (its rows are rolled back, the journal says why); warnings are listed in work/dbcheck/<car>.txt.
Usage: py dbcheck.py <MediaName> [...]   re-runs the "after" checks on installed cars (read-only).
"""
import collections
import os
import sqlite3
import sys

# columns the porter changes after inserting, on purpose: (table lower, column lower)
ALLOWED = {("data_car", c) for c in ("makeid", "makename", "displayname", "modelshort", "basecost", "ispurchased",
                                     "isinstalled", "thumbnail")} | \
          {("data_car_buckets", "carbucket"), ("data_engine", "medianame")}
NONE = (None, 0, -1, "", "0")


class Validator:
    def __init__(self, porter):
        self.p = porter
        self.types2 = {}
        self.domain = {}
        self.reset()

    def reset(self):
        self.inserted = []          # (table, cols, rows, replace)
        self.errors, self.warnings = [], []

    # ───────────── before ─────────────

    def _types(self, t):
        if t not in self.types2:
            self.types2[t] = {r[1]: (r[2] or "").upper() for r in self.p.fh2.execute("PRAGMA table_info(%s)" % _qi(t))}
        return self.types2[t]

    def _domain(self, t, c):
        """Values FH2 uses in a small enumeration column (<= 40 distinct over >= 50 rows), else None."""
        k = (t, c)
        if k not in self.domain:
            q = "SELECT COUNT(*), COUNT(DISTINCT %s) FROM %s" % (_qi(c), _qi(t))
            n, d = self.p.fh2.execute(q).fetchone()
            self.domain[k] = None
            if n >= 50 and d <= 40 and c.lower().endswith(("id", "type", "class")):
                self.domain[k] = {r[0] for r in self.p.fh2.execute("SELECT DISTINCT %s FROM %s" % (_qi(c), _qi(t)))}
        return self.domain[k]

    def before(self, t, c3, rows, replace):
        self.inserted.append((t, list(c3), [list(r) for r in rows], replace))
        types = self._types(t)
        for ci, c in enumerate(c3):
            vals = [r[ci] for r in rows]
            if c not in types:
                data = [v for v in vals if v not in NONE]
                if data:
                    self.warnings.append("%s.%s: FH2 has no such column, %d row(s) lose %r" % (t, c, len(data), data[:3]))
                continue
            ty = types[c]
            for v in vals:
                if isinstance(v, str) and ("INT" in ty or ty in ("REAL", "FLOAT", "DOUBLE", "NUMERIC")) and not _num(v):
                    self.errors.append("%s.%s: text %r in a %s column" % (t, c, v[:40], ty))
                    break
            dom = self._domain(t, c) if ci > 0 else None
            if dom:
                odd = sorted({v for v in vals if v not in dom and v not in NONE}, key=str)
                if odd:
                    self.warnings.append("%s.%s: value(s) %s never used by FH2 (FH2 uses %s)" % (
                        t, c, odd[:5], sorted(dom, key=str)[:12]))

    # ───────────── after ─────────────

    def after(self, car_id):
        db = self.p.fh2
        seen = set()
        for t, c3, rows, replace in self.inserted:
            types = self._types(t)
            use = [i for i, c in enumerate(c3) if c in types]
            keep = [i for i in use if (t.lower(), c3[i].lower()) not in ALLOWED]
            for r in rows:
                key = (t, tuple(r[i] for i in keep))
                if key in seen:
                    continue
                seen.add(key)
                where = " AND ".join("%s IS ?" % _qi(c3[i]) for i in keep)
                if db.execute("SELECT 1 FROM %s WHERE %s LIMIT 1" % (_qi(t), where), [r[i] for i in keep]).fetchone():
                    continue
                if not replace:
                    # INSERT OR IGNORE: FH2 already had a row with this key; it must still be there
                    k0 = c3[use[0]]
                    if db.execute("SELECT 1 FROM %s WHERE %s IS ?" % (_qi(t), _qi(k0)), (r[use[0]],)).fetchone():
                        continue
                self.errors.append("%s: row %s=%r not in the database as inserted%s" % (
                    t, c3[use[0]], r[use[0]], self._closest(t, c3, r, keep)))
            # references
            for ci, c in enumerate(c3):
                if ci == 0 or c not in types:
                    continue
                target = self.p.ref_target(c, t)
                if not target or target[0] not in self.p.common:
                    continue
                tt, kc = target
                for v in {r[ci] for r in rows} - set(NONE):
                    if db.execute("SELECT 1 FROM %s WHERE %s = ?" % (_qi(tt), _qi(kc)), (v,)).fetchone():
                        continue
                    # the target table is guessed from the column name (StockWheelID -> WheelExceptions instead of
                    # List_Wheels); a broken reference is one FH3 resolves in that table and FH2 doesn't
                    if self.p.fh3.execute("SELECT 1 FROM %s WHERE %s = ?" % (_qi(tt), _qi(kc)), (v,)).fetchone():
                        self.errors.append("%s.%s = %r: no %s row with %s = %r (FH3 has one)" % (t, c, v, tt, kc, v))
        self._car_rules(car_id)
        return self.errors, self.warnings

    def _closest(self, t, c3, r, keep):
        """The FH2 row with the same first column: which columns differ."""
        k0 = c3[keep[0]]
        row = self.p.fh2.execute("SELECT %s FROM %s WHERE %s IS ? LIMIT 1" % (
            ",".join(_qi(c3[i]) for i in keep), _qi(t), _qi(k0)), (r[keep[0]],)).fetchone()
        if not row:
            return " (no row with that %s)" % k0
        diff = ["%s %r -> %r" % (c3[i], r[i], v) for i, v in zip(keep, row) if v != r[i]]
        return " (differs: %s)" % ", ".join(diff[:6])

    def _car_rules(self, car_id):
        db = self.p.fh2
        cols = [r[1] for r in db.execute("PRAGMA table_info(Data_Car)")]
        row = db.execute("SELECT * FROM Data_Car WHERE Id = ?", (car_id,)).fetchone()
        if not row:
            self.errors.append("Data_Car: no row for id %d" % car_id)
            return
        car = dict(zip(cols, row))
        mk = db.execute("SELECT DisplayName FROM List_CarMake WHERE ID = ?", (car["MakeID"],)).fetchone()
        if not mk:
            self.errors.append("Data_Car.MakeID %r: no List_CarMake row" % car["MakeID"])
        elif car["MakeName"] != mk[0]:
            self.errors.append("Data_Car.MakeName %r != List_CarMake.DisplayName %r (menu placement)" % (car["MakeName"], mk[0]))
        for c in ("DisplayName", "ModelShort"):
            v = car.get(c)
            if not v:
                self.errors.append("Data_Car.%s is empty" % c)
            elif isinstance(v, str) and v.startswith("_&") and _en_text("Data_Car", v) is None:
                self.errors.append("Data_Car.%s %r has no text in the English string table" % (c, v))
        if (car.get("BaseCost") or 0) <= 1:
            self.errors.append("Data_Car.BaseCost %r" % car.get("BaseCost"))
        buckets2 = {r[0] for r in db.execute("SELECT DISTINCT CarBucket FROM Data_Car_Buckets WHERE CarId NOT IN (%s)" % ",".join(
            str(i) for i in self._ported_ids() | {car_id}))}
        for (b,) in db.execute("SELECT CarBucket FROM Data_Car_Buckets WHERE CarId = ?", (car_id,)):
            if b not in buckets2:
                self.errors.append("Data_Car_Buckets.CarBucket %r is not an FH2 category" % b)
        banks = {f[3:-5].lower() for f in os.listdir(self.p.audio_dir()) if f.startswith("PG_") and f.endswith(".bank")}
        for eid, media in db.execute("SELECT EngineID, MediaName FROM Data_Engine WHERE EngineID IN "
                                     "(SELECT EngineID FROM List_UpgradeEngine WHERE Ordinal = ?)", (car_id,)):
            if (media or "").lower() not in banks:
                self.errors.append("Data_Engine %d MediaName %r has no FH2 sound bank (silent car)" % (eid, media))

    def _ported_ids(self):
        return {c.get("id") for c in self.p.j["cars"].values() if c.get("status") == "ported" and c.get("id")}


_EN = {}


def _en_text(table, sid):
    """Text of an FH2 string id ("_&n", key = low 16 bits) in EN.zip's <table>.str, or None."""
    import zipfile
    import fh3port
    import strtables
    if table not in _EN:
        _EN[table] = {}
        zp = os.path.join(fh3port.STRINGTABLES, "EN.zip")
        if os.path.exists(zp):
            with zipfile.ZipFile(zp) as z:
                n = next((x for x in z.namelist() if x.lower() == table.lower() + ".str"), None)
                if n:
                    _EN[table] = strtables.Lsb2(z.read(n)).strings
    try:
        return _EN[table].get(int(sid[2:]) & 0xFFFF)
    except ValueError:
        return None


def _qi(n):
    return '"%s"' % n.replace('"', '""')


def _num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def write_report(work, media, errors, warnings):
    d = os.path.join(work, "dbcheck")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, media + ".txt"), "w", encoding="utf-8") as f:
        f.write("%s: %d errors, %d warnings\n" % (media, len(errors), len(warnings)))
        for e in errors:
            f.write("ERROR   " + e + "\n")
        for w in warnings:
            f.write("warning " + w + "\n")


def main():
    """Re-checks installed cars: the 'after' rules on Data_Car plus references of all rows keyed by the car."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fh3port as P
    porter = P.Porter(P.journal(), P.FH2_DB)
    total = collections.Counter()
    for media in sys.argv[1:]:
        row = porter.fh2.execute("SELECT Id FROM Data_Car WHERE MediaName = ? COLLATE NOCASE", (media,)).fetchone()
        if not row:
            print(media, "not in the database"); total["error"] += 1
            continue
        v = Validator(porter)
        for t, c in porter.car_tables.items():
            if c in porter.cols2[t]:
                cc = [r[1] for r in porter.fh2.execute("PRAGMA table_info(%s)" % _qi(t))]
                rows = porter.fh2.execute("SELECT * FROM %s WHERE %s = ?" % (_qi(t), _qi(c)), (row[0],)).fetchall()
                if rows:
                    v.inserted.append((t, cc, [list(r) for r in rows], True))
        errors, warnings = v.after(row[0])
        total["error"] += len(errors)
        print("%-24s %d errors, %d warnings" % (media, len(errors), len(warnings)))
        for e in errors:
            print("   ERROR", e)
    sys.exit(1 if total["error"] else 0)


if __name__ == "__main__":
    main()
