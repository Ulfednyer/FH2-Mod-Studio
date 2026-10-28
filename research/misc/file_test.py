# Writes extreme test values into both track settings files (restore with: distance_patch.py apply 2).
import os, re

MEDIA = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media"
TEST = [("GrassFadeStartDistance", "value", "3.000000"), ("GrassFadeEndDistance", "value", "5.000000"),
        ("ShadowEnds", "InGameShadowEnd", "5.000000")]
for rel in (r"tracks\anthem\tracksettings.xml", r"tracks\AnthemTrackSettings.xml"):
    p = os.path.join(MEDIA, rel)
    text = open(p, encoding="utf-8", newline="").read()
    for tag, attr, val in TEST:
        rx = re.compile(r'(<%s\b[^>]*?\b%s=")(-?[0-9.]+)(")' % (tag, attr))
        text, n = rx.subn(lambda m: m.group(1) + val + m.group(3), text, count=1)
        print("%-34s %s@%s = %s (%s)" % (rel, tag, attr, val, "ok" if n else "NOT FOUND"))
    open(p, "w", encoding="utf-8", newline="").write(text)
