import sys, zipfile, struct, subprocess, os
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import fh3port, geom, mtpr
S = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad"
out = os.path.join(S, "tire_c_conv.zip")
rc, log, _ = fh3port.convert_zip(r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires\tire_c.zip", "fh3tire_c", out)
print("cli rc", rc)
B = zipfile.ZipFile(out).read("tireL_c.modelbin")
C = geom.convert_model(B)
A = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
ha, ea = geom.read_bundle(A)
hc, ec = geom.read_bundle(C)
print("blob versions FH2 :", [(e.tag, e.ver) for e in ea][:6], "...")
print("blob versions conv:", [(e.tag, e.ver) for e in ec][:6], "...")
ma = geom.parse_mesh(next(e for e in ea if e.tag == "Mesh").data, (1, 7))
mc_e = next(e for e in ec if e.tag == "Mesh")
mc = geom.parse_mesh(mc_e.data, mc_e.ver)
print("mesh0 FH2 bindings", ma["bindings"], "end", ma["end"], "| conv bindings", mc["bindings"], "len", len(mc_e.data))
va = [e for e in ea if e.tag == "VerB"]; vc = [e for e in ec if e.tag == "VerB"]
for a, c in zip(va, vc):
    print("VerB FH2 hdr", struct.unpack_from("<IIHHI", a.data), " conv hdr", struct.unpack_from("<IIHHI", c.data))
na = struct.unpack_from("<I", va[0].data)[0]; nc = struct.unpack_from("<I", vc[0].data)[0]
pa = np.frombuffer(va[0].data[16:16 + na * 12], "<f4").reshape(-1, 3)
pc = np.frombuffer(vc[0].data[16:16 + nc * 12], "<f4").reshape(-1, 3)
A1 = np.frombuffer(va[1].data[16:16 + na * 36], np.uint8).reshape(-1, 36)
sc = struct.unpack_from("<H", vc[1].data, 8)[0]
C1 = np.frombuffer(vc[1].data[16:16 + nc * sc], np.uint8).reshape(-1, sc)
uva = A1[:, 8:12].copy().view("<u2").astype(float) / 65535; uvc = C1[:, 8:12].copy().view("<u2").astype(float) / 65535
N = 1500
ka = np.hstack([pa, uva * 0.1]); kc = np.hstack([pc, uvc * 0.1])
idx = np.array([np.argmin(((ka - k) ** 2).sum(1)) for k in kc[:N]])
print("position err max %.6f" % np.abs(pa[idx] - pc[:N]).max())
na_ = A1[idx, 0:8].copy().view("<f2").astype(float); nc_ = C1[:N, 0:8].copy().view("<f2").astype(float)
print("normal err mean %.4f max %.4f" % (np.abs(na_ - nc_).mean(), np.abs(na_ - nc_).max()))
ta = A1[idx, 20:28].copy().view("<f2").astype(float); tc = C1[:N, 24:32].copy().view("<f2").astype(float)
print("tangent0 err mean %.4f max %.4f" % (np.abs(ta - tc).mean(), np.abs(ta - tc).max()))
vla = next(e for e in ea if e.tag == "VLay"); vlc = next(e for e in ec if e.tag == "VLay")
print("VLay FH2 :", [(x["sem"], x["idx"], x["fmt"], x["code"]) for x in geom.parse_vlay(vla.data)])
print("VLay conv:", [(x["sem"], x["idx"], x["fmt"], x["code"]) for x in geom.parse_vlay(vlc.data)])
print("modl", [e.data.hex() for e in ec if e.tag == "Modl"], "skel len", [len(e.data) for e in ec if e.tag == "Skel"])
mtpr.strict_check(C)
print("bundle re-parse OK, total", struct.unpack_from("<I", C, 12)[0], "len", len(C))
