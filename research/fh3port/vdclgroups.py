"""VDCL metadata of FH2 shaders, per group (2-byte group header + (hash, mask) list). usage: vdclgroups.py <shader> [...]"""
import zipfile, struct, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
FH3PORT = os.path.abspath(os.path.join(HERE, "..", "..", "fh3port"))
if FH3PORT not in sys.path:
    sys.path.insert(0, FH3PORT)

import bundle

_Z = None
_names = None


def get_shaders_zip():
    global _Z, _names
    if _Z is None:
        try:
            import fh3port
            shaders_path = fh3port.FH2_SHADERS
        except Exception:
            shaders_path = None
        if not shaders_path or not os.path.exists(shaders_path):
            raise FileNotFoundError("FH2 Shaders.zip not found: %s" % shaders_path)
        _Z = zipfile.ZipFile(shaders_path)
        _names = {n.lower().rsplit("/", 1)[-1]: n for n in _Z.namelist()}
    return _Z, _names


def groups(d):
    out = []
    for b in bundle.parse(d):
        for mt, mv, md in b.metas:
            if mt[::-1] != b"VDCL":
                continue
            p, outer = 0, 1
            if mv >= 3:
                outer = struct.unpack_from("<i", md, p)[0]; p += 4
            for _ in range(outer):
                hdr = None
                if mv >= 4:
                    hdr = md[p:p + 2].hex(); p += 2
                n = struct.unpack_from("<i", md, p)[0]; p += 4
                ms = []
                for _ in range(n):
                    h, f = struct.unpack_from("<Ii", md, p); p += 8
                    ms.append((hex(h), hex(f)))
                out.append((b.tag[::-1], mv, hdr, ms))
    return out


if __name__ == "__main__":
    z, names = get_shaders_zip()
    for sh in sys.argv[1:]:
        d = z.read(names[sh.lower() + ".shaderbin"])
        print("==", sh)
        for tag, mv, hdr, ms in groups(d):
            print("  blob %s VDCL v%d group %s: %s" % (tag, mv, hdr, " ".join("%s" % f for h, f in ms)))
