import re, glob, os, struct
dmp = max(glob.glob(r"C:\Users\opsuc\Downloads\amzimuth\data\logs\*.dmp"), key=os.path.getmtime)
d = open(dmp, "rb").read()
print("dump", dmp, len(d))
pat = re.compile(rb"(?i)game:\\[\w\\\.+ -]{6,200}\.(?:shaderbin|materialbin|modelbin|swatchbin|carbin|xml|zip)")
hits = {}
for m in pat.finditer(d):
    s = m.group().decode("latin1")
    hits.setdefault(s.lower(), []).append(m.start())
for s, offs in hits.items():
    if any(k in s for k in ("nsx", "fh3tire", "wet_c", "b_horizon", "acu_")):
        print(len(offs), s)
# minidump: exception stream -> faulting thread context -> stack memory
sig, ver, nstreams, rva = struct.unpack_from("<IIII", d, 0)
streams = {}
for i in range(nstreams):
    t, size, srva = struct.unpack_from("<III", d, rva + 12 * i)
    streams[t] = (size, srva)
print("streams", sorted(streams))
size, srva = streams[6]
tid = struct.unpack_from("<I", d, srva)[0]
ctx_size, ctx_rva = struct.unpack_from("<II", d, srva + 8 + 152)
rsp = struct.unpack_from("<Q", d, ctx_rva + 0x98)[0]
rip = struct.unpack_from("<Q", d, ctx_rva + 0xF8)[0]
print("thread %d rip %x rsp %x" % (tid, rip, rsp))
# memory list (stream 5) or memory64 (9): find the stack range containing rsp
mem = []
if 5 in streams:
    size, mrva = streams[5]
    n = struct.unpack_from("<I", d, mrva)[0]
    for i in range(n):
        start, dsize, drva = struct.unpack_from("<QII", d, mrva + 4 + 16 * i)
        mem.append((start, dsize, drva))
if 9 in streams:
    size, mrva = streams[9]
    n, base = struct.unpack_from("<QQ", d, mrva)
    off = base
    for i in range(n):
        start, dsize = struct.unpack_from("<QQ", d, mrva + 16 + 16 * i)
        mem.append((start, dsize, off))
        off += dsize
for start, dsize, drva in mem:
    if start <= rsp < start + dsize:
        stack = d[drva + (rsp - start): drva + dsize]
        print("stack bytes from rsp:", len(stack))
        strs = [m.group().decode("latin1") for m in re.finditer(rb"[\x20-\x7e]{8,200}", stack)]
        print("strings on the crashing thread's stack:")
        for s in strs[:60]:
            print("   ", s)
        # return addresses into the game image
        rets = [struct.unpack_from("<Q", stack, i)[0] for i in range(0, min(len(stack), 0x3000), 8)]
        print("game return addrs:", [hex(r) for r in rets if 0x140001000 <= r < 0x143000000][:40])
        break
