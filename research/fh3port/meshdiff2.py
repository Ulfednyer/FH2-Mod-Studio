import sys, zipfile, struct
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
A = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
B = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")


def blob(d, want, idx=0):
    n = 0
    for tag, ver, e, doff, size in mtpr.blobs(d):
        if tag[::-1].decode("latin1") == want:
            if n == idx:
                return d[doff:doff + size], ver
            n += 1


def show(label, data, w=32):
    print(label)
    for off in range(0, len(data), w):
        c = data[off:off + w]
        print("   %04x  %-96s %s" % (off, c.hex(" "), "".join(chr(x) if 32 <= x < 127 else "." for x in c)))


for tag, idx in (("Mesh", 0), ("VLay", 0), ("VLay", 1), ("Modl", 0)):
    a, va = blob(A, tag, idx)
    b, vb = blob(B, tag, idx)
    show("== FH2 %s#%d v%d.%d (%d bytes)" % (tag, idx, *va, len(a)), a)
    show("== FH3 %s#%d v%d.%d (%d bytes)" % (tag, idx, *vb, len(b)), b)
for idx in (0, 1):
    a, _ = blob(A, "VerB", idx)
    b, _ = blob(B, "VerB", idx)
    print("VerB#%d FH2 head %s" % (idx, a[:48].hex(" ")))
    print("VerB#%d FH3 head %s" % (idx, b[:48].hex(" ")))
