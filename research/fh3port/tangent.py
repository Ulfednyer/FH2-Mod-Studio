import sys, zipfile, struct
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
A = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
B = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
def blobs(d, tag):
    return [(d[doff:doff + size], ver) for t, ver, e, doff, size in mtpr.blobs(d) if t[::-1] == tag]
a0, a1 = [x[0] for x in blobs(A, b"VerB")]
b0, b1 = [x[0] for x in blobs(B, b"VerB")]
na, nb = struct.unpack_from("<I", a0)[0], struct.unpack_from("<I", b0)[0]
# FH2 positions float3, FH3 snorm16x4 * scale + offset (from tyre mesh tail)
pa = np.frombuffer(a0[16:16 + na * 12], dtype="<f4").reshape(-1, 3)
rb = np.frombuffer(b0[16:16 + nb * 8], dtype="<i2").reshape(-1, 4).astype(np.float64) / 32767.0
scale = np.array([0.5001193284988403, 0.2266305387020111, 0.22663027048110962]); off = np.array([0.5000050067901611, 0.0, 0.0])
pb = rb[:, :3] * scale + off
# match each FH3 vertex to the nearest FH2 vertex (same tyre, slightly different vertex sets)
from math import inf
idx = np.array([np.argmin(((pa - p) ** 2).sum(1)) for p in pb[:400]])
dist = np.sqrt(((pa[idx] - pb[:400]) ** 2).sum(1))
print("position match: median dist %.6f, max %.6f (over 400 verts)" % (np.median(dist), dist.max()))
# FH2 slot1: NORMAL half4, TEX0-2 u16x2, TANGENT0 half4, TANGENT1 half4 (stride 36)
A1 = np.frombuffer(a1[16:16 + na * 36], dtype=np.uint8).reshape(-1, 36)
B1 = np.frombuffer(b1[16:16 + nb * 32], dtype=np.uint8).reshape(-1, 32)
na_t0 = A1[:, 20:28].copy().view("<f2").astype(np.float32)
nb_raw = B1[:, 20:24].copy().view("<u4")[:, 0]
cands = {
    "unorm*2-1": lambda v: np.stack([((v >> s) & 1023) / 1023.0 * 2 - 1 for s in (0, 10, 20)] + [((v >> 30) & 3) / 3.0 * 2 - 1], 1),
    "snorm10": lambda v: np.stack([np.where(((v >> s) & 1023) >= 512, ((v >> s) & 1023).astype(np.int64) - 1024, (v >> s) & 1023) / 511.0 for s in (0, 10, 20)] + [((v >> 30) & 3).astype(np.float64)], 1),
}
fh2_t0 = na_t0[idx]
for name, f in cands.items():
    t = f(nb_raw[:400].astype(np.int64))
    err = np.abs(t[:, :3] - fh2_t0[:, :3]).mean()
    print("%-10s mean |err| xyz %.4f  w sample FH3 %s FH2 %s" % (name, err, np.round(t[:5, 3], 3), np.round(fh2_t0[:5, 3], 3)))
print("FH2 tangent0 sample", np.round(fh2_t0[:3], 4))
print("FH3 raw tangent0", [hex(x) for x in nb_raw[:3]], "decoded unorm", np.round(cands["unorm*2-1"](nb_raw[:3].astype(np.int64)), 4))
# MBuf headers
for label, d in (("FH2", A), ("FH3", B)):
    m = blobs(d, b"MBuf")[0][0]
    print(label, "MBuf", len(m), "header", m[:32].hex(" "))
