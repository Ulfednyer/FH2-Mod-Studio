import re
data = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\forza_durango_release_final.exe", "rb").read()
pats = [b"CarTrackOffsets", b"UpgradeFrontOffset", b"List_UpgradeTireCompound", b"List_UpgradeSpringDamper", b"List_UpgradeAntiSway", b"List_UpgradeEngineTurboTwin", b"TireCompound"]
seen = set()
for m in re.finditer(rb"[\x20-\x7e]{6,}", data):
    s = m.group()
    if any(p in s for p in pats) and s not in seen:
        seen.add(s)
        print(hex(m.start()), s.decode()[:400])
for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data):
    s = m.group().decode("utf-16le")
    if any(p.decode() in s for p in pats) and s not in seen:
        seen.add(s)
        print(hex(m.start()), "W", s[:400])

