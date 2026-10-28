import re, os, struct
d = open(r"C:\Users\opsuc\Downloads\amzimuth\data\logs\20261018T184924-651-31104.dmp", "rb").read()
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount"
# manifest lines as loaded (the parser stripped '=' / quotes oddly in the dump view, so read raw)
lines = re.findall(rb'<Zip[^>]{0,300}/>', d)
print("zip lines in dump:", len(lines))
seen = {}
for l in lines:
    s = l.decode("latin1")
    p = re.search(r'path\W+(game:[^"\s]+)', s, re.I)
    if p:
        seen.setdefault(p.group(1).lower(), s)
for key in [k for k in seen if any(x in k for x in ("acu_nsx", "rcfh3", "fh3tire", "tire_wet", "tire_b_h", "cars\\_library\\textures.zip"))]:
    s = seen[key]
    nums = dict(re.findall(r'(dirstart|dirsize|direntries)\W+(\d+)', s))
    path = os.path.join(M, key.strip().split("game:\\", 1)[1].strip())
    actual = None
    if os.path.exists(path):
        with open(path, "rb") as f:
            f.seek(-22, 2); e = f.read(22)
        cds, cdo = struct.unpack_from("<II", e, 12); cnt = struct.unpack_from("<H", e, 10)[0]
        actual = {"dirstart": str(cdo), "dirsize": str(cds + 22), "direntries": str(cnt)}
    print(key, "\n   dump:", nums, "\n   file:", actual, "MATCH" if actual == nums else "DIFFERENT")
# strings near the crash: the failing path is in the loader's stack buffer
for m in re.finditer(rb'game:\\media\\[\w\\\.+ -]{3,120}\.zip', d, re.I):
    pass
tail = [m.group().decode("latin1") for m in re.finditer(rb'game:\\media\\[\w\\\.+ -]{3,120}\.zip\x00', d, re.I)]
print("NUL-terminated zip paths (C strings, e.g. stack buffers):", len(tail))
for t in dict.fromkeys(tail):
    print("  ", t)

