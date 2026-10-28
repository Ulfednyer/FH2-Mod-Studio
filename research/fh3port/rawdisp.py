import struct, re, sys
sys.path.insert(0, "")
data = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\forza_durango_release_final.exe", "rb").read()
pe = struct.unpack_from("<I", data, 0x3C)[0]
nsec = struct.unpack_from("<H", data, pe + 6)[0]
opt = struct.unpack_from("<H", data, pe + 20)[0]
secs = []
for i in range(nsec):
    o = pe + 24 + opt + i * 40
    name = data[o:o + 8].rstrip(b"\0").decode()
    vsz, va, rsz, raw = struct.unpack_from("<IIII", data, o + 8)
    secs.append((name, va, raw, rsz))
text = [s for s in secs if s[0] == ".text"][0]
_, va, raw, rsz = text
FIELDS = {0x50AC: "stockNorm", 0x50B0: "fitNorm", 0x50C4: "FrontOff", 0x50C8: "RearOff", 0x50CC: "UpgFront", 0x50D0: "UpgRear", 0x50D9: "flag"}
for disp, name in FIELDS.items():
    pat = struct.pack("<I", disp)
    hits = [m.start() for m in re.finditer(re.escape(pat), data[raw:raw + rsz])]
    print(name, hex(disp), len(hits), " ".join(hex(0x140000000 + va + h) for h in hits[:40]))
