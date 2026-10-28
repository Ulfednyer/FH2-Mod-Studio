# Lists gamedb columns that look like draw/LOD/clip/fade distances, with value ranges.
import re, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql")
from fh2sql import Conn

PAT = re.compile(r"(draw|view|clip|fade|cull|lod|stream|visib|far|near).*(dist|range|radius|scale)|dist.*(lod|fade|draw|cull)|^lod|farclip|nearclip|drawdist", re.I)
c = Conn()
tables = [r[0] for r in c.call("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")["results"][0]["rows"]]
for t in tables:
    cols = [r[1] for r in c.call('PRAGMA table_info("%s");' % t)["results"][0]["rows"]]
    hits = [col for col in cols if PAT.search(col)]
    if not hits:
        continue
    agg = ", ".join('MIN("%s"), MAX("%s")' % (h, h) for h in hits)
    r = c.call('SELECT COUNT(*), %s FROM "%s";' % (agg, t))
    row = r["results"][0]["rows"][0] if not r["error"] else ["?"]
    rng = ["%s[%s..%s]" % (h, row[1 + 2 * i], row[2 + 2 * i]) for i, h in enumerate(hits)] if len(row) > 1 else hits
    print("%-40s rows=%-5s %s" % (t, row[0], "  ".join(rng)))
