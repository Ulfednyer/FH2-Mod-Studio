"""Run fh3port.convert_zip for a car into scratch and save the zip zfight receives (to test zfight changes on real
inputs). usage: capture_zfight_input.py <FH3 MediaName> <out_dir>"""
import os
import shutil
import sys

sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import fh3port as P

media, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
orig = P.zfight.fix_zip


def capture(src, dst):
    shutil.copyfile(src, os.path.join(out_dir, media + "_zfight_in.zip"))
    return orig(src, dst)


P.zfight.fix_zip = capture
rc, log, missing = P.convert_zip(os.path.join(P.FH3, "cars", media + ".zip"), media, os.path.join(out_dir, media + "_full.zip"))
print(media, "rc", rc)
