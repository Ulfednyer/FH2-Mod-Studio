# Lists entries in game zips whose names suggest render / LOD / distance config; also greps small XML/INI entries.
import os, re, sys, zipfile
from collections import Counter

root = sys.argv[1]
NAME = re.compile(r"lod|dist|render|grass|foliage|terrain|stream|cull|clip|fade|draw|scenario|tod|world|setting|config", re.I)
TEXT = re.compile(rb"(?i)<\s*(\w*(?:Dist|LOD|Clip|Fade|Cull|DrawRange|StreamRadius)\w*)[\s>]|(\w*(?:Dist|Clip|Fade|Cull)\w*)\s*=\s*\"")
tags = Counter()
for dp, _, fs in os.walk(root):
    for f in fs:
        if not f.lower().endswith(".zip"):
            continue
        p = os.path.join(dp, f)
        try:
            z = zipfile.ZipFile(p)
        except (zipfile.BadZipFile, OSError):
            continue
        infos = z.infolist()
        exts = Counter(os.path.splitext(i.filename)[1].lower() for i in infos)
        hits = [i.filename for i in infos if NAME.search(i.filename)]
        print("%s: %d entries %s%s" % (os.path.relpath(p, root), len(infos), dict(exts.most_common(4)),
              ("\n    " + "\n    ".join(hits[:8])) if hits else ""))
        for i in infos:
            if i.filename.lower().endswith((".xml", ".ini", ".txt", ".cfg")) and i.file_size < 2_000_000:
                for m in TEXT.finditer(z.read(i)):
                    tags[(m.group(1) or m.group(2)).decode(errors="replace") + "  (" + os.path.basename(i.filename) + ")"] += 1
print("\n--- distance-ish tags/attributes in zipped xml/ini:")
for t, n in tags.most_common(60):
    print("  %4d  %s" % (n, t))
