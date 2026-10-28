import zipfile, struct
z3 = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\stripped\stringtables\en.zip")
d = z3.read("data_car.str")
h = struct.unpack_from("<6I", d, 0)
print("header", h)
n = h[5]
ents = [struct.unpack_from("<II", d, 24 + i * 8) for i in range(n)]
print("first entries", [(hex(k), o) for k, o in ents[:6]], "last", [(hex(k), o) for k, o in ents[-3:]])
key = 7441166985706553632 & 0xFFFFFFFF
hit = [e for e in ents if e[0] == key]
print("nsx key", hex(key), hit)
pool = 24 + n * 8
print("pool start", pool, "remaining", len(d) - pool)
for base in (pool,):
    for k, o in ents[:4] + hit:
        for scale in (1, 2):
            p = base + o * scale
            s = d[p:p + 80]
            try:
                t = s.decode("utf-16le").split("\x00")[0]
            except Exception:
                t = None
            print(" scale", scale, hex(k), o, repr(t), s[:24].hex(" "))
