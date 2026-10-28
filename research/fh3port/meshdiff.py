import sys, zipfile, struct
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
A = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
B = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires\tire_c.zip")
print("FH3 tire_c entries:", B.namelist())
B = B.read([n for n in B.namelist() if n.lower().startswith("tirel")][0])


def info(label, d):
    print("==", label, len(d), "header:", d[:24].hex(" "))
    out = []
    for tag, ver, e, doff, size in mtpr.blobs(d):
        meta = struct.unpack_from("<H", d, e + 6)[0]
        moff = struct.unpack_from("<I", d, e + 8)[0]
        out.append((tag[::-1].decode("latin1"), ver, doff, size, moff, meta))
        print("   %s v%d.%d data@%x size %d meta@%x n=%d" % (tag[::-1].decode("latin1"), ver[0], ver[1], doff, size, moff, meta))
    return out


ia, ib = info("FH2 tire_c", A), info("FH3 tire_c", B)
for (ta, va, da, sa, *_), (tb, vb, db, sb, *_) in zip(ia, ib):
    if ta in ("Modl", "Mesh", "Skel", "VLay") and (sa != sb or A[da:da + sa] != B[db:db + sb]):
        print("\n--- %s FH2 v%d.%d %d bytes | FH3 v%d.%d %d bytes" % (ta, *va, sa, *vb, sb))
        print("FH2:", A[da:da + min(sa, 160)].hex(" "))
        print("FH3:", B[db:db + min(sb, 160)].hex(" "))
        if ta == "Mesh":
            break
