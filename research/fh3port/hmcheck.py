import struct, os
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount"
d = open(os.path.join(M, "hash.manifest"), "rb").read()
print("size", len(d), "size%12", len(d) % 12)


def fh(s, lower=False, seed=5381):
    h = seed & 0xFFFFFFFF
    for ch in s.encode("latin1"):
        c = ord(chr(ch).lower()) if lower else ch
        h ^= (c + (h >> 2) + (h << 5)) & 0xFFFFFFFF
        h &= 0xFFFFFFFF
    j = h
    for ch in s.encode("latin1"):
        c = ord(chr(ch).lower()) if lower else ch
        j ^= (c + (j >> 2) + (j << 5)) & 0xFFFFFFFF
        j &= 0xFFFFFFFF
    return h | (j << 32)


for layout in ("<QI", "<IQ"):
    recs = [struct.unpack_from(layout, d, i) for i in range(0, len(d) - len(d) % 12, 12)]
    keys = {(r[0] if layout == "<QI" else r[1]): (r[1] if layout == "<QI" else r[0]) for r in recs}
    vals = {}
    for v in keys.values():
        vals[v] = vals.get(v, 0) + 1
    print(layout, "records", len(recs), "distinct values", len(vals), "top values", sorted(vals.items(), key=lambda x: -x[1])[:6])
    tests = []
    for base in ("media\\zipmanifest.xml", "media\\cars\\CHE_CorvetteZ06_15.zip", "media\\stripped\\gamedbRC.slt", "hash.manifest",
                 "forza_durango_release_final.exe", "AppxManifest.xml", "media\\_library\\textures.zip", "media\\cars"):
        for v in (base, base.lower(), base.upper(), base.replace("\\", "/"), ".\\" + base, "\\" + base, "game:\\" + base, "g:\\" + base):
            for lower in (False, True):
                tests.append((v, lower))
    hits = [(v, lw, keys[fh(v, lw)]) for v, lw in tests if fh(v, lw) in keys]
    print("  hits:", hits[:20])
