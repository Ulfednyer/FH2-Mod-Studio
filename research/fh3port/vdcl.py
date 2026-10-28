import sys, zipfile, struct, collections


def vdcl_masks(d):
    """All VDCL vertex-input masks of a shaderbin (bundle 1.0 or 1.1)."""
    if d[:4] != b"burG":
        return []
    maj, mi = d[4], d[5]
    if (maj, mi) == (1, 0):
        count = struct.unpack_from("<H", d, 6)[0]; eo = 16
    else:
        count = struct.unpack_from("<I", d, 16)[0]; eo = 20
    out = []
    for i in range(count):
        tag, vM, vm, mc, mo = struct.unpack_from("<4sBBHI", d, eo + 24 * i)
        for k in range(mc):
            mt, sv, rel = struct.unpack_from("<4sHH", d, mo + 8 * k)
            if mt[::-1] != b"VDCL":
                continue
            ver = sv & 15; p = mo + 8 * k + rel
            outer = 1
            if ver >= 3:
                outer = struct.unpack_from("<i", d, p)[0]; p += 4
            for _ in range(outer):
                if ver >= 4:
                    p += 2
                n = struct.unpack_from("<i", d, p)[0]; p += 4
                for _ in range(n):
                    h, f = struct.unpack_from("<Ii", d, p); p += 8
                    out.append(f)
    return out


if __name__ == "__main__":
    masks = collections.Counter(); nsh = 0
    for zp in sys.argv[1:]:
        z = zipfile.ZipFile(zp)
        for n in z.namelist():
            if n.lower().endswith(".shaderbin"):
                m = vdcl_masks(z.read(n)); nsh += 1
                for f in set(m):
                    masks[f] += 1
    print("shaderbins", nsh, "distinct masks", len(masks))
