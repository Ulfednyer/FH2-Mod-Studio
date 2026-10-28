import zipfile, re
from collections import Counter
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"
srcs = {
    "converted tire_WET_c": (M + r"\_library\scene\tires\tire_WET_c.zip", "tireR_WET_c.modelbin"),
    "FH3 tire_WET_c": (r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires\tire_WET_c.zip", "tireR_WET_c.modelbin"),
    "FH2 tire_c": (M + r"\_library\scene\tires\tire_c.zip", "tireL_c.modelbin"),
    "FH2 Z06 body": (M + r"\CHE_CorvetteZ06_15.zip", None),
}
for label, (zp, name) in srcs.items():
    z = zipfile.ZipFile(zp)
    if name is None:
        name = max((n for n in z.namelist() if n.endswith(".modelbin")), key=lambda n: z.getinfo(n).file_size)
    d = z.read(name)
    tags = Counter(m.group().decode() for m in re.finditer(rb"(?:LTAM|RPTM|ITAM|burG|ldoM|hseM|yaLV|BreV|BxdI|emaN|TSTA|DIUG)", d))
    print("== %s %s %d bytes tags %s" % (label, name, len(d), dict(tags)))
    p = d.find(b"RPTM")
    if p >= 0:
        print("   first RPTM at %x: %s" % (p, d[p:p + 48].hex(" ")))
    p = d.find(b"ITAM")
    if p >= 0:
        print("   first ITAM at %x: %s" % (p, d[p:p + 48].hex(" ")))
