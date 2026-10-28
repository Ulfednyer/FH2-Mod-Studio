"""Minimal minidump reader: exception thread's stack -> candidate return addresses inside the game module.
usage: mdstack.py <file.dmp> [module-substring]"""
import struct, sys

d = open(sys.argv[1], "rb").read()
modkey = (sys.argv[2] if len(sys.argv) > 2 else "forza").lower()
sig, ver, nstreams, rva = struct.unpack_from("<IIII", d, 0)
streams = {}
for i in range(nstreams):
    t, size, r = struct.unpack_from("<III", d, rva + 12 * i)
    streams.setdefault(t, []).append((r, size))


def utf16(r):
    n = struct.unpack_from("<I", d, r)[0]
    return d[r + 4:r + 4 + n].decode("utf-16le")


mods = []
for r, s in streams.get(4, []):
    n = struct.unpack_from("<I", d, r)[0]
    for i in range(n):
        base, size = struct.unpack_from("<QI", d, r + 4 + 108 * i)
        name = utf16(struct.unpack_from("<I", d, r + 4 + 108 * i + 20)[0])
        mods.append((base, size, name))
game = next((m for m in mods if modkey in m[2].lower()), None)
print("module", game and (hex(game[0]), hex(game[1]), game[2]))
mem = []
for r, s in streams.get(9, []):
    n, base_rva = struct.unpack_from("<QQ", d, r)
    p = base_rva
    for i in range(n):
        start, size = struct.unpack_from("<QQ", d, r + 16 + 16 * i)
        mem.append((start, size, p)); p += size
for r, s in streams.get(5, []):
    n = struct.unpack_from("<I", d, r)[0]
    for i in range(n):
        start, size, mr = struct.unpack_from("<QII", d, r + 4 + 16 * i)
        mem.append((start, size, mr))


def read(addr, n):
    for start, size, p in mem:
        if start <= addr and addr + n <= start + size:
            return d[p + addr - start:p + addr - start + n]
    return None


r, s = streams[6][0]
tid = struct.unpack_from("<I", d, r)[0]
code, flags, rec, addr = struct.unpack_from("<IIQQ", d, r + 8)
ctx_size, ctx_rva = struct.unpack_from("<II", d, r + 8 + 152)
print("exception thread", tid, "code", hex(code), "address", hex(addr), "context", ctx_size)
ctx = d[ctx_rva:ctx_rva + ctx_size]
names = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi"]
regs = {n: struct.unpack_from("<Q", ctx, 0x78 + 8 * i)[0] for i, n in enumerate(names)}
rip = struct.unpack_from("<Q", ctx, 0xF8)[0]
print("rip", hex(rip), {k: hex(v) for k, v in regs.items()})
gbase, gsize = (game[0], game[1]) if game else (0x140000000, 0x4000000)
rsp = regs["rsp"]
hits = []
for off in range(0, 0x3000, 8):
    q = read(rsp + off, 8)
    if q is None:
        break
    v = struct.unpack("<Q", q)[0]
    if gbase <= v < gbase + gsize:
        hits.append((off, v - gbase + 0x140000000))
print("stack hits (rsp offset, address at image base 0x140000000):")
for off, v in hits[:60]:
    print("  +%04x %s" % (off, hex(v)))
