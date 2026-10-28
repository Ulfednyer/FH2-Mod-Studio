import zipfile, struct
z2 = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\stripped\stringtables\EN.zip")
z3 = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\stripped\stringtables\en.zip")
for label, d in (("FH2 Data_Car.str", z2.read("Data_Car.str")), ("FH3 data_car.str", z3.read("data_car.str"))):
    print("==", label, len(d))
    print(" head:", d[:64].hex(" "))
    words = struct.unpack_from("<16I", d, 0)
    print(" u32:", words)
for label, d, key, w in (("FH2", z2.read("Data_Car.str"), 3444174200, 4), ("FH3", z3.read("data_car.str"), 7441166985706553632, 8)):
    pat = struct.pack("<I" if w == 4 else "<Q", key)
    print(label, "key found at", d.find(pat))
    lo = struct.pack("<I", key & 0xFFFFFFFF); hi = struct.pack("<I", key >> 32)
    print(label, "low32 at", d.find(lo), "high32 at", d.find(hi))
