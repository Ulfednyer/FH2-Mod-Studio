import zipfile, struct
FH2 = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\stringtables\EN.zip"
FH3 = r"C:\Games\Forza Horizon 3\media\stripped\stringtables\en.zip"
z2, z3 = zipfile.ZipFile(FH2), zipfile.ZipFile(FH3)
def find(z, needles, label):
    for i in z.infolist():
        d = z.read(i)
        for n, pat in needles:
            p = d.find(pat)
            if p >= 0:
                print(label, i.filename, i.file_size, n, "at", p, d[max(0, p - 24):p + 64])
find(z2, [("z06 name u32", struct.pack("<I", 3444174200)), ("chevrolet utf16", "Corvette Z06".encode("utf-16le")), ("chevrolet utf8", b"Corvette Z06")], "FH2")
find(z3, [("nsx name u64", struct.pack("<Q", 7441166985706553632)), ("nsx utf16", "NSX".encode("utf-16le")), ("nsx utf8", b"Acura NSX")], "FH3")
d = z2.read("CarClasses.str"); print("FH2 CarClasses.str head:", d[:96])
print("FH3 entries:", [(i.filename, i.file_size) for i in z3.infolist()][:12])
