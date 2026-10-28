"""scan_frame.py <pid> <vftable hex>  - finds objects with that vftable in private RW memory, prints +8 and +0x10 fields."""
import ctypes, struct, sys
from ctypes import wintypes


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong), ("AllocationProtect", wintypes.DWORD),
                ("__a", wintypes.DWORD), ("RegionSize", ctypes.c_ulonglong), ("State", wintypes.DWORD), ("Protect", wintypes.DWORD),
                ("Type", wintypes.DWORD), ("__b", wintypes.DWORD)]


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
pid, vt = int(sys.argv[1]), int(sys.argv[2], 16)
h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
needle = struct.pack("<Q", vt)
addr, mbi, scanned, hits = 0, MBI(), 0, []
CHUNK = 64 << 20
while k32.VirtualQueryEx(h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
    base, size = mbi.BaseAddress, mbi.RegionSize
    if mbi.State == 0x1000 and mbi.Type == 0x20000 and mbi.Protect in (0x04, 0x40):  # committed private RW / RWX
        for off in range(0, size, CHUNK):
            n = min(CHUNK, size - off)
            buf = ctypes.create_string_buffer(n)
            got = ctypes.c_size_t()
            if not k32.ReadProcessMemory(h, base + off, buf, n, ctypes.byref(got)):
                continue
            data = buf.raw[: got.value]
            scanned += len(data)
            i = data.find(needle)
            while i >= 0:
                if i % 8 == 0 and i + 0x18 <= len(data):
                    w, hgt, cnt, q = struct.unpack_from("<IIII", data, i + 8)
                    hits.append((base + off + i, w, hgt, cnt, q))
                i = data.find(needle, i + 1)
    addr = base + size
print("scanned %d MB" % (scanned >> 20))
for a, w, hgt, cnt, q in hits[:10]:
    print("Frame11 @%X  +8=%d +0xC=%d  SampleDesc={Count=%d, Quality=%d}" % (a, w, hgt, cnt, q))
