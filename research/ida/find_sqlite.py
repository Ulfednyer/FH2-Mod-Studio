# Runs inside IDA. Finds SQLite internals and game-side DB code via string references.
import re
from collections import Counter
import idautils, idc, ida_funcs, ida_name

PATTERNS = [
    r"gamedb", r"\.slt\b", r"SQLite format 3", r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [0-9a-f]{20,}",
    r"^3\.\d+\.\d+", r"near \"%T\": syntax error", r"cannot open file at line", r"misuse at line",
    r"API call with %s database connection", r"unsupported file format", r"statement aborts at",
    r"database schema has changed", r"^PRAGMA ", r"sqlite_master", r"unable to open database",
    r"journal_mode", r"^:memory:$", r"^ATTACH ", r"sqlite3_", r"^BEGIN", r"^COMMIT",
]
SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|WITH)\b", re.I)


def funcs_of(ea, limit=6):
    out = []
    for x in idautils.XrefsTo(ea):
        f = ida_funcs.get_func(x.frm)
        out.append("%s@%X" % (ida_name.get_name(f.start_ea), f.start_ea) if f else "data@%X" % x.frm)
    return sorted(set(out))[:limit]


sql_funcs, sql_count = Counter(), 0
for s in idautils.Strings():
    text = str(s)
    for p in PATTERNS:
        if re.search(p, text, re.I):
            print("%X %-70r -> %s" % (s.ea, text[:70], ", ".join(funcs_of(s.ea))))
            break
    if SQL.match(text) and len(text) > 15:
        sql_count += 1
        for f in funcs_of(s.ea, 50):
            sql_funcs[f] += 1
print("\nSQL-looking strings: %d; top referencing functions:" % sql_count)
for f, n in sql_funcs.most_common(25):
    print("  %3d  %s" % (n, f))
