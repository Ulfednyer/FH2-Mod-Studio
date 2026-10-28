import zipfile
FH2LIB = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\Materials.zip"
FH3LIB = r"C:\Games\Forza Horizon 3\media\cars\_library\Materials.zip"
CONV = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\fh3tire_wet_c.zip"
z2 = zipfile.ZipFile(FH2LIB)
n2 = [n for n in z2.namelist() if "tiretread_c" in n.lower()]
print("FH2 tiretread:", n2[:5])
z3 = zipfile.ZipFile(FH3LIB)
n3 = [n for n in z3.namelist() if "tiretread_c_wet" in n.lower()]
print("FH3:", n3)
def hx(label, d, n=480):
    print("==", label, len(d))
    for off in range(0, min(len(d), n), 32):
        chunk = d[off:off + 32]
        print("  %04x  %-96s %s" % (off, chunk.hex(" "), "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)))
hx("FH2 native " + n2[0], z2.read(n2[0]))
hx("FH3 original " + n3[0], z3.read(n3[0]))
zc = zipfile.ZipFile(CONV)
hx("converted", zc.read("materials/genericassetmaterials/tiretread_c_wet.materialbin"))
