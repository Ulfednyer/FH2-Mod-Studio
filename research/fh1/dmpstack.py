"""Minimal minidump reader: exception record, registers, and stack words that point into the game image.
py dmpstack.py <dump> [game_base_hex] [words]"""
import struct, sys

d = open(sys.argv[1], "rb").read()
sig, ver, nstreams, sdir = struct.unpack_from("<IIII", d, 0)
streams = {}
for i in range(nstreams):
    t, size, rva = struct.unpack_from("<III", d, sdir + 12 * i)
    streams.setdefault(t, []).append((size, rva))

mem = []  # (start, size, rva)
if 9 in streams:  # Memory64ListStream
    size, rva = streams[9][0]
    n, base_rva = struct.unpack_from("<QQ", d, rva)
    p = base_rva
    for i in range(n):
        st, sz = struct.unpack_from("<QQ", d, rva + 16 + 16 * i)
        mem.append((st, sz, p)); p += sz
if 5 in streams:  # MemoryListStream
    size, rva = streams[5][0]
    n = struct.unpack_from("<I", d, rva)[0]
    for i in range(n):
        st, sz, r = struct.unpack_from("<QII", d, rva + 4 + 16 * i)
        mem.append((st, sz, r))


def rd(addr, n):
    for st, sz, r in mem:
        if st <= addr and addr + n <= st + sz:
            return d[r + addr - st:r + addr - st + n]
    return None


mods = []
if 4 in streams:
    size, rva = streams[4][0]
    n = struct.unpack_from("<I", d, rva)[0]
    for i in range(n):
        p = rva + 4 + 108 * i
        base, sz = struct.unpack_from("<QI", d, p)
        nrva = struct.unpack_from("<I", d, p + 20)[0]
        ln = struct.unpack_from("<I", d, nrva)[0]
        name = d[nrva + 4:nrva + 4 + ln].decode("utf-16le")
        mods.append((base, sz, name))


def modof(a):
    for b, s, n in mods:
        if b <= a < b + s:
            return n.split("\\")[-1], a - b
    return None, None


size, rva = streams[6][0]
tid, _, code, flags, rec, addr = struct.unpack_from("<IIIIQQ", d, rva)
nparams = struct.unpack_from("<I", d, rva + 32)[0]
params = struct.unpack_from("<%dQ" % nparams, d, rva + 40)
csize, crva = struct.unpack_from("<II", d, rva + 8 + 152)
print("thread %d code %#x at %#x %s params %s" % (tid, code, addr, modof(addr), [hex(x) for x in params]))
ctx = d[crva:crva + csize]
names = "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
regs = struct.unpack_from("<16Q", ctx, 0x78)
rip = struct.unpack_from("<Q", ctx, 0xF8)[0]
for nm, v in zip(names, regs):
    print("%s=%#x %s" % (nm, v, modof(v) if modof(v)[0] else ""))
print("rip=%#x %s" % (rip, modof(rip)))
gbase = int(sys.argv[2], 16) if len(sys.argv) > 2 else None
for b, s, n in mods:
    if "game" in n.lower() or n.lower().endswith(".exe"):
        print("module %#x %#x %s" % (b, s, n))
rsp = regs[4]
words = int(sys.argv[3]) if len(sys.argv) > 3 else 400
for k in range(words):
    w = rd(rsp + 8 * k, 8)
    if w is None:
        break
    v = struct.unpack("<Q", w)[0]
    mn, off = modof(v)
    if mn:
        print("  rsp+%#5x  %#x  %s+%#x" % (8 * k, v, mn, off))
    elif gbase and gbase <= v < gbase + 0x4000000:
        print("  rsp+%#5x  %#x  game+%#x (ida %#x)" % (8 * k, v, v - gbase, 0x140000000 + v - gbase))
