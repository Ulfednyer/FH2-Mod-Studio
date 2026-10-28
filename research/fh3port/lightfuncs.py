"""Extract the car light-function table (name -> id, 'Offset_<Name>' + u64 id pairs) from FH2 and FH3 executables."""
import struct, json, sys

def table(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<Q", d, pe + 24 + 24)[0]
    secs = []
    for i in range(nsec):
        o = pe + 24 + opt + 40 * i
        vs, va, rawsz, rawp = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, rawsz, rawp))
    off2va = lambda off: next(base + va + off - rp for va, rs, rp in secs if rp <= off < rp + rs)
    def va2off(v):
        v -= base
        return next((rp + v - va for va, rs, rp in secs if va <= v < va + rs), None)
    sva = off2va(d.find(b"Offset_BrakeLightAmount\x00"))
    p = d.find(struct.pack("<Q", sva))
    out = {}
    while True:
        ptr, idx = struct.unpack_from("<QQ", d, p)
        o = va2off(ptr) if ptr > base else None
        if o is None: break
        s = d[o:d.index(b"\x00", o)].decode("latin1")
        if not s.startswith("Offset_"): break
        out[s[7:]] = idx; p += 16
    return out

if __name__ == "__main__":
    fh2 = table(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\forza_durango_release_final.exe")
    fh3 = table(r"C:\Games\Forza Horizon 3\forza_x64_release.exe")
    print("FH2", len(fh2), "FH3", len(fh3))
    for n in sorted(set(fh2) | set(fh3), key=lambda n: fh3.get(n, 1000 + fh2.get(n, 0))):
        a, b = fh2.get(n), fh3.get(n)
        print("%-32s FH2 %4s  FH3 %4s %s" % (n, a, b, "" if a == b else "<-- differs"))
    if len(sys.argv) > 1:
        json.dump({"fh2": fh2, "fh3": fh3}, open(sys.argv[1], "w"), indent=1)
