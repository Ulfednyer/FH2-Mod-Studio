import zipfile, subprocess, os
S = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad\conv"
CLI = r"C:\Users\opsuc\Downloads\Forza Horizon 2 Convertor\ForzaToolsCli.exe"
src = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\stripped\RC6.zip")
lib = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\_library\Textures.zip")
want = [n for n in lib.namelist() if "acu_caliperlf_003_ao_ao" in n.lower() or n.lower().endswith("plate_ao.swatchbin")]
print("lib names:", want)
fake = os.path.join(S, "swfake.zip")
with zipfile.ZipFile(fake, "w", zipfile.ZIP_STORED) as z:
    for n in ("Thumbnail_2352_Big.swatchbin", "Thumbnail_2352_Small.swatchbin", "B_2352.swatchbin"):
        z.writestr("textures/" + n, src.read(n))
    for n in want:
        z.writestr("textures/lib/" + n.split("/")[-1], lib.read(n))
print("in headers:", {n: src.read(n)[:6] for n in ("Thumbnail_2352_Big.swatchbin",)})
out = os.path.join(S, "swfake_out.zip")
r = subprocess.run([CLI, "fix-materials", "--car", fake, "--car-name", "swfake", "--fh3-lib", r"C:\Games\Forza Horizon 3\media\cars\_library",
                    "--fh2-lib", r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library",
                    "--fh2-shaders", r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\_library\Shaders.zip", "--out", out],
                   capture_output=True, text=True)
print("rc", r.returncode, "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "archive" not in l)[-1500:])
if os.path.exists(out):
    o = zipfile.ZipFile(out)
    for n in o.namelist():
        print("out", n, o.read(n)[:6], len(o.read(n)))
