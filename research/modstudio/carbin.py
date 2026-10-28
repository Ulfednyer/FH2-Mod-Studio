import zipfile, struct, re
z = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\CHE_CorvetteZ06_15.zip")
for name in ("CHE_CorvetteZ06_15.carbin", "CHE_CorvetteZ06_15.carbin_debug"):
    d = z.read(name)
    print("==", name, len(d))
    for v in (2177000, 2177001, 2177, 2180401, 2180402, 2177500):
        hits = [m.start() for m in re.finditer(re.escape(struct.pack("<I", v)), d)]
        print("  int", v, hits[:10])
    for m in re.finditer(rb"[\x20-\x7e]{4,}", d):
        s = m.group()
        if re.search(rb"bumper|Bumper|body|Body|part|Part|upgrade|Upgrade", s):
            print("  str %x %s" % (m.start(), s[:100].decode()))
    if name.endswith("_debug"):
        print(d[:1099].decode("latin1"))
