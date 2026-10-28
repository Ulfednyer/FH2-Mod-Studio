"""Orthographic z-buffer render of converted (FH2-format) modelbins, colour = material, simple shading.
usage: render.py <car.zip> <out.png> <view: front|back|side|top> <name-substring,...> [lodbit] [W]
Writes a PNG (no matplotlib/PIL) and prints the colour legend."""
import zipfile, struct, sys, zlib, os
CULL = os.environ.get("CULL", "")  # pos/neg: drop triangles of that screen winding (back-face test)
import numpy as np
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom, slod

PALETTE = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240),
           (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40), (255, 250, 200),
           (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180), (0, 0, 128), (128, 128, 128), (255, 255, 255),
           (100, 100, 255), (255, 100, 100), (100, 255, 100)]


def load(zp, keys, lodbit):
    z = zipfile.ZipFile(zp)
    tris, mats_of = [], []
    names = []
    for n in z.namelist():
        if not n.lower().endswith(".modelbin") or not any(k in n.lower() for k in keys):
            continue
        hs, ents = geom.read_bundle(z.read(n))
        mats = slod.material_paths(ents)
        bufs = {geom.blob_id(e): e for e in ents if e.tag == "VerB"}
        ibs = {geom.blob_id(e): e for e in ents if e.tag == "IndB"}
        for e in ents:
            if e.tag != "Mesh":
                continue
            mid = struct.unpack_from("<h", e.data, 0)[0]
            flags = struct.unpack_from("<H", e.data, 4)[0]
            if lodbit and not flags & lodbit:
                continue
            m = geom.parse_mesh(e.data, e.ver)
            pb = None
            for bid, slot, stride, off in m["bindings"]:
                b = bufs.get(bid)
                if b is None:
                    continue
                cnt, sz, st, nel, fmt = struct.unpack_from("<IIHHI", b.data, 0)
                if fmt == 6 and st == 12:
                    pb = (np.frombuffer(b.data[16:16 + cnt * 12], "<f4").reshape(-1, 3), off // stride if stride else 0)
                    break
            ib = ibs.get(m["index_buffer"])
            if pb is None or ib is None:
                continue
            cnt, sz, st = struct.unpack_from("<IIH", ib.data, 0)
            idx = np.frombuffer(ib.data[16:16 + cnt * st], "<u4" if st == 4 else "<u2").astype(np.int64)
            idx = idx[m["start_index"]:m["start_index"] + m["index_count"]] + m["base_vertex"] + pb[1]
            idx = idx[: len(idx) // 3 * 3].reshape(-1, 3)
            idx = idx[(idx < len(pb[0])).all(1)]
            mat = n.split("/")[-1].replace(".modelbin", "") + " | " + mats.get(mid, "?").split("\\")[-1].replace(".materialbin", "")
            if mat not in names:
                names.append(mat)
            tris.append(pb[0][idx]); mats_of.append(np.full(len(idx), names.index(mat)))
    return np.concatenate(tris), np.concatenate(mats_of), names


def png(path, img):
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                          + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def render(T, M, view, W):
    # axes: x = width, y = up, z = length (guess); view picks (horizontal, vertical, depth, depth sign)
    ax = {"front": (0, 1, 2, 1), "back": (0, 1, 2, -1), "side": (2, 1, 0, 1), "top": (0, 2, 1, -1)}[view]
    P = T[:, :, [ax[0], ax[1], ax[2]]].astype(np.float64)
    P[:, :, 2] *= ax[3]
    if view == "back":
        P[:, :, 0] *= -1
    lo, hi = P[:, :, :2].reshape(-1, 2).min(0), P[:, :, :2].reshape(-1, 2).max(0)
    scale = (W - 20) / max(hi[0] - lo[0], 1e-6)
    H = int((hi[1] - lo[1]) * scale) + 20
    X = (P[:, :, 0] - lo[0]) * scale + 10
    Y = H - ((P[:, :, 1] - lo[1]) * scale + 10)
    Zd = P[:, :, 2]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    shade = 0.45 + 0.55 * np.abs(n[:, ax[2]])
    zbuf = np.full((H, W), -np.inf); img = np.full((H, W, 3), 40, np.uint8)
    for i in range(len(T)):
        x0, x1 = int(max(X[i].min(), 0)), int(min(X[i].max() + 1, W - 1))
        y0, y1 = int(max(Y[i].min(), 0)), int(min(Y[i].max() + 1, H - 1))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax_, ay), (bx, by), (cx, cy) = zip(X[i], Y[i])
        d = (by - cy) * (ax_ - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-9 or (CULL == "pos" and d > 0) or (CULL == "neg" and d < 0):
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / d
        l2 = ((cy - ay) * (xs - cx) + (ax_ - cx) * (ys - cy)) / d
        l3 = 1 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not inside.any():
            continue
        z = l1 * Zd[i, 0] + l2 * Zd[i, 1] + l3 * Zd[i, 2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z > sub)
        sub[upd] = z[upd]
        col = np.array(PALETTE[M[i] % len(PALETTE)]) * shade[i]
        img[y0:y1 + 1, x0:x1 + 1][upd] = col.astype(np.uint8)
    return img


if __name__ == "__main__":
    zp, out, view, keys = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].lower().split(",")
    lodbit = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0x2
    W = int(sys.argv[6]) if len(sys.argv) > 6 else 1400
    T, M, names = load(zp, keys, lodbit)
    png(out, render(T, M, view, W))
    for i, nm in enumerate(names):
        print("%-14s %s" % (PALETTE[i % len(PALETTE)], nm))
