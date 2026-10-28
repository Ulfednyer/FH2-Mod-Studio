import sys, zipfile, struct
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr
A = zipfile.ZipFile(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
B = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\_library\scene\tires\tire_c.zip").read("tireL_c.modelbin")
def blobs(d, tag):
    return [d[doff:doff + size] for t, ver, e, doff, size in mtpr.blobs(d) if t[::-1] == tag]
a0, a1 = blobs(A, b"VerB"); b0, b1 = blobs(B, b"VerB")
na, nb = struct.unpack_from("<I", a0)[0], struct.unpack_from("<I", b0)[0]
pa = np.frombuffer(a0[16:16 + na * 12], dtype="<f4").reshape(-1, 3).astype(np.float64)
rb = np.frombuffer(b0[16:16 + nb * 8], dtype="<i2").reshape(-1, 4).astype(np.float64) / 32767.0
scale = np.array([0.5001193284988403, 0.2266305387020111, 0.22663027048110962]); off = np.array([0.5000050067901611, 0.0, 0.0])
pb = rb[:, :3] * scale + off
A1 = np.frombuffer(a1[16:16 + na * 36], dtype=np.uint8).reshape(-1, 36)
B1 = np.frombuffer(b1[16:16 + nb * 32], dtype=np.uint8).reshape(-1, 32)
uva = A1[:, 8:12].copy().view("<u2").astype(np.float64) / 65535   # TEX0 (after NORMAL half4)
uvb = B1[:, 4:8].copy().view("<u2").astype(np.float64) / 65535    # TEX0 (after NORMAL rg16)
# match by position + uv (seam duplicates differ in uv)
N = 1500
key_a = np.hstack([pa, uva * 0.1]); key_b = np.hstack([pb, uvb * 0.1])
idx = np.array([np.argmin(((key_a - k) ** 2).sum(1)) for k in key_b[:N]])
print("match dist max", np.sqrt(((key_a[idx] - key_b[:N]) ** 2).sum(1)).max())
# normals: FH2 half4; FH3 x = pos.w, yz = rg16 snorm
nfa = A1[:, 0:8].copy().view("<f2").astype(np.float64)[idx]
nyz = B1[:N, 0:4].copy().view("<i2").astype(np.float64) / 32767.0
nfb = np.column_stack([rb[:N, 3], nyz])
print("normal  mean |err| %.4f max %.4f" % (np.abs(nfb - nfa[:, :3]).mean(), np.abs(nfb - nfa[:, :3]).max()), "FH2 normal.w values", np.unique(np.round(nfa[:, 3], 3))[:5])
# tangents
for slot, (oa, ob) in enumerate(((20, 20), (28, 24))):
    ta = A1[:, oa:oa + 8].copy().view("<f2").astype(np.float64)[idx]
    v = B1[:N, ob:ob + 4].copy().view("<u4")[:, 0].astype(np.int64)
    xyz = np.stack([((v >> s) & 1023) / 1023.0 * 2 - 1 for s in (0, 10, 20)], 1)
    xyz /= np.linalg.norm(xyz, axis=1, keepdims=True)
    w = np.where(((v >> 30) & 3) >= 2, 1.0, -1.0)
    err = np.abs(xyz - ta[:, :3]).mean(); werr = (w != np.sign(ta[:, 3])).mean()
    print("tangent%d mean |err| %.4f, w mismatch %.1f%%, raw w bits %s" % (slot, err, werr * 100, np.unique((v >> 30) & 3)))
