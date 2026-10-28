import re, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql")
from fh2sql import Conn

c = Conn()
tables = [r[0] for r in c.call("SELECT tbl_name FROM sqlite_master WHERE type='table' AND (sql LIKE '%turbo%' OR sql LIKE '%drop%');")["results"][0]["rows"]]
for t in tables:
    cols = c.call('PRAGMA table_info("%s");' % t)["results"][0]["rows"]
    n = c.call('SELECT COUNT(*) FROM "%s";' % t)["results"][0]["rows"][0][0]
    hits = ["%s:%s" % (r[1], r[2]) for r in cols if re.search(r"turbo|drop|boost|falloff", r[1], re.I)]
    print("%-32s rows=%-5s cols=%-3d %s" % (t, n, len(cols), hits))
