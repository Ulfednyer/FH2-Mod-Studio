import struct, os, collections
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount"
d = open(os.path.join(M, "hash.manifest"), "rb").read()
keys = {struct.unpack_from("<Q", d, i)[0]: struct.unpack_from("<I", d, i + 8)[0] for i in range(0, len(d), 12)}


def fh(s):
    s = s.lower().encode("latin1")
    h = 5381
    for c in s:
        h = (h ^ ((c + (h >> 2) + (h << 5)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    j = h
    for c in s:
        j = (j ^ ((c + (j >> 2) + (j << 5)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return h | (j << 32)


files, dirs = [], []
for root, ds, fs in os.walk(M):
    for x in ds:
        dirs.append(os.path.relpath(os.path.join(root, x), M))
    for x in fs:
        files.append(os.path.relpath(os.path.join(root, x), M))
hit_f = [f for f in files if fh(f) in keys]
hit_d = [x for x in dirs if fh(x) in keys]
print("disk files", len(files), "in manifest", len(hit_f), "| dirs", len(dirs), "in manifest", len(hit_d))
print("records not matched by any disk file/dir:", len(keys) - len(hit_f) - len(hit_d))
by_dir = collections.defaultdict(collections.Counter)
for f in hit_f:
    by_dir[os.path.dirname(f).lower()][keys[fh(f)]] += 1
for k in sorted(by_dir):
    if any(s in k for s in ("cars", "stripped", "physics", "tires", "media")) and k.count("\\") <= 4:
        print("%-45s %s" % (k, by_dir[k].most_common(4)))
for f in ("media\\cars\\che_corvettez06_15.zip", "media\\cars\\acu_integrar_01.zip", "media\\cars\\_library\\textures.zip", "media\\stripped\\rc14.zip"):
    print(f, keys.get(fh(f)), os.path.getsize(os.path.join(M, f)) if os.path.exists(os.path.join(M, f)) else None)
print("not-in-manifest disk files (sample):", [f for f in files if fh(f) not in keys][:15])
