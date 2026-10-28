# Greps loose XML/INI/TXT under media for distance / LOD / clip / fade settings (tag or attribute names + values).
import os, re, sys

root = sys.argv[1]
SKIP = {"cars", "audio", "speech", "drivers", "ui", "Renderscenariosmod Backup"}
PAT = re.compile(r"""<\s*(\w*(?:Dist|LOD|Lod|Clip|Fade|Cull|Range|Radius|FarPlane|NearPlane)\w*)([^>]*)>|(\w*(?:Dist|LOD|Lod|Clip|Fade|Cull|FarPlane)\w*)\s*=\s*"([^"]*)\"""")
for dp, dirs, fs in os.walk(root):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in fs:
        if not f.lower().endswith((".xml", ".ini", ".txt")):
            continue
        p = os.path.join(dp, f)
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        hits = []
        for m in PAT.finditer(text):
            s = (m.group(1) + m.group(2)) if m.group(1) else "%s=\"%s\"" % (m.group(3), m.group(4))
            s = re.sub(r"\s+", " ", s.strip())[:110]
            if s not in hits:
                hits.append(s)
        if hits:
            print("== %s" % os.path.relpath(p, root))
            for h in hits[:14]:
                print("    " + h)
            if len(hits) > 14:
                print("    ... +%d more" % (len(hits) - 14))
