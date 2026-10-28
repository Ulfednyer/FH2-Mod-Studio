"""Every Texture2D path referenced by a car (materials + instances): does FH2 have it, and is it loadable?"""
import zipfile, struct, sys, os, collections, glob
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr, tex
MEDIA = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
zp, car = sys.argv[1], sys.argv[2].lower()
z = zipfile.ZipFile(zp)
cnames = {n.lower(): n for n in z.namelist()}
lib = {}
for p in glob.glob(os.path.join(MEDIA, "cars", "_library", "Textures*.zip")):
    zz = zipfile.ZipFile(p)
    for n in zz.namelist():
        lib.setdefault(n.lower(), (zz, n))


def s7(b, p):
    n = s = 0
    while True:
        c = b[p]; p += 1; n |= (c & 0x7f) << s; s += 7
        if not c & 0x80: return b[p:p + n].decode("latin1")


refs = collections.Counter()


def walk(d):
    for tag, ver, ep, doff, size in mtpr.blobs(d):
        b = d[doff:doff + size]
        t = tag[::-1]
        if t == b"MTPR":
            ps, _ = mtpr.parse_params(b, None)
            for s, e, maj, mn, h, typ in ps:
                if typ == 6:
                    refs[s7(b, s + 7 + (16 if maj >= 3 else 0)).lower()] += 1
        elif t == b"MatI":
            walk(b)


for n in z.namelist():
    if n.lower().endswith((".modelbin", ".materialbin")):
        walk(z.read(n))
pre_car = "game:\\media\\cars\\%s\\" % car
pre_lib = "game:\\media\\cars\\_library\\textures\\"
stat = collections.Counter(); bad = []
for p, c in refs.items():
    if p.startswith(pre_car):
        key = p[len(pre_car):].replace("\\", "/"); src = "car"
        data = z.read(cnames[key]) if key in cnames else None
    elif p.startswith(pre_lib):
        key = p[len(pre_lib):].replace("\\", "/"); src = "lib"
        hit = lib.get(key)
        data = hit[0].read(hit[1]) if hit else None
    else:
        src = "other"; data = None
    if data is None:
        stat[src + " MISSING"] += 1; bad.append((c, p)); continue
    lay = tex._layout(data)
    kind = "none" if not lay else ("xbox" if lay[1] == (2, 0) else "pc")
    stat[src + " " + kind] += 1
    if not lay:
        bad.append((c, "UNREADABLE " + p))
print(dict(stat))
for c, p in sorted(bad, reverse=True)[:40]: print(c, p)
