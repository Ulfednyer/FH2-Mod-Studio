"""Find D3D11_INPUT_ELEMENT_DESC arrays (32-byte entries: name ptr, index, DXGI format, slot, offset, class, step) in an
Azimuth minidump and print each array with resolved semantic names; flags arrays with duplicate (name, index).
usage: mddesc.py <file.dmp> [max]"""
import struct, sys, collections

d = open(sys.argv[1], "rb").read()
MAXN = int(sys.argv[2]) if len(sys.argv) > 2 else 40
sig, ver, nstreams, sdir = struct.unpack_from("<IIII", d, 0)
ranges = []   # (va, size, file offset)
for i in range(nstreams):
    st, size, rva = struct.unpack_from("<III", d, sdir + 12 * i)
    if st == 9:   # Memory64ListStream
        n, base = struct.unpack_from("<QQ", d, rva)
        off = base
        for k in range(n):
            va, sz = struct.unpack_from("<QQ", d, rva + 16 + 16 * k)
            ranges.append((va, sz, off))
            off += sz
    elif st == 5:   # MemoryListStream (stacks and selected regions)
        n = struct.unpack_from("<I", d, rva)[0]
        for k in range(n):
            va, sz, r = struct.unpack_from("<QII", d, rva + 4 + 16 * k)
            ranges.append((va, sz, r))
ranges.sort()
print("memory ranges", len(ranges), "bytes", sum(r[1] for r in ranges))


def read(va, n):
    for a, sz, off in ranges:
        if a <= va < a + sz:
            if va + n <= a + sz:
                return d[off + va - a: off + va - a + n]
            return None
    return None


def cstr(va):
    b = read(va, 24)
    if not b:
        return None
    e = b.find(b"\0")
    s = b[:e if e >= 0 else 24]
    return s.decode("latin1") if s and all(32 < c < 127 for c in s) else None


SEM = {"POSITION", "NORMAL", "TEXCOORD", "TANGENT", "COLOR", "BINORMAL"}
found = 0
for a, sz, off in ranges:
    blob = d[off:off + sz]
    # entries with offset == -1 (append) and class 0, step 0: bytes 20..32 = ff ff ff ff 00.. 00..
    p = 0
    marker = b"\xff\xff\xff\xff" + b"\0" * 8
    while True:
        p = blob.find(marker, p)
        if p < 0:
            break
        start = p - 20
        if start < 0 or (a + start) % 8:
            p += 4
            continue
        # walk back to the first entry of the array
        s = start
        while s - 32 >= 0 and blob[s - 32 + 20:s - 32 + 32] == marker:
            s -= 32
        ents = []
        q = s
        while q + 32 <= len(blob) and blob[q + 20:q + 32] == marker:
            ptr, idx, fmt, slot = struct.unpack_from("<QIII", blob, q)
            ents.append((cstr(ptr), idx, fmt, slot))
            q += 32
        p = q
        if len(ents) < 3 or not all(e[0] in SEM for e in ents):
            continue
        keys = [(e[0], e[1]) for e in ents]
        dup = len(set(keys)) != len(keys)
        found += 1
        if dup or found <= MAXN:
            print("%s 0x%x: %s" % ("DUP" if dup else "ok ", a + s, " ".join("%s%d:%d@%d" % e for e in ents)))
print("arrays", found)
