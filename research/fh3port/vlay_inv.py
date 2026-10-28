import sys, zipfile, struct, glob, os
from collections import Counter
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr

def parse_vlay(b):
    p = 0
    nsem = struct.unpack_from("<H", b, p)[0]; p += 2
    sems = []
    for _ in range(nsem):
        n = struct.unpack_from("<I", b, p)[0]; p += 4
        sems.append(b[p:p + n].decode("latin1")); p += n
    nel = struct.unpack_from("<H", b, p)[0]; p += 2
    els = []
    for _ in range(nel):
        sem, idx, slot, fmt, off, inst = struct.unpack_from("<HHIIiI", b, p); p += 20
        els.append((sems[sem], idx, slot, fmt))
    codes = list(struct.unpack_from("<%dI" % nel, b, p)); p += 4 * nel
    rest = b[p:]
    return els, codes, rest

def inventory(zips):
    c = Counter(); layouts = Counter()
    for zp in zips:
        z = zipfile.ZipFile(zp)
        for n in z.namelist():
            if not n.endswith(".modelbin"):
                continue
            d = z.read(n)
            try:
                for tag, ver, e, doff, size in mtpr.blobs(d):
                    if tag == b"yaLV":
                        els, codes, rest = parse_vlay(d[doff:doff + size])
                        for el, code in zip(els, codes):
                            c[(el[0], el[2], el[3], code)] += 1
                        layouts[tuple((el[0], el[1], el[2], el[3], code) for el, code in zip(els, codes)) + (rest.hex(),)] += 1
            except Exception as ex:
                c[("ERR", str(ex)[:40])] += 1
    return c, layouts

M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"
fh2_zips = [M + r"\CHE_CorvetteZ06_15.zip", M + r"\ACU_IntegraR_01.zip", M + r"\HON_NSXR_92.zip"] + glob.glob(M + r"\_library\scene\wheels\*.zip")[:5]
fh2_zips = [z for z in fh2_zips if os.path.exists(z)]
a, la = inventory(fh2_zips)
b, lb = inventory([r"C:\Games\Forza Horizon 3\media\cars\ACU_NSX_16.zip"])
print("FH2 (semantic, slot, dxgi, code):")
for k, v in sorted(a.items(), key=str): print("   ", k, v)
print("FH3 NSX (semantic, slot, dxgi, code):")
for k, v in sorted(b.items(), key=str): print("   ", k, v, "" if k in a else "  <-- not used by FH2")
print("FH2 distinct layouts %d, FH3 NSX distinct layouts %d" % (len(la), len(lb)))
print("FH2 layout trailers:", Counter(k[-1] for k in la).most_common(8))
print("FH3 layout trailers:", Counter(k[-1] for k in lb).most_common(8))

def short(layout):
    els = layout[:-1]
    return " ".join("%s%d@%d:%d" % (e[0][:3], e[1], e[2], e[4]) for e in els) + "  -> 0x" + bytes.fromhex(layout[-1])[::-1].hex()
print("\nFH2 layouts:")
for l in la: print("   ", short(l))
print("FH3 layouts:")
for l in lb: print("   ", short(l))
