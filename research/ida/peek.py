"""peek.py <pid> <hexaddr> <size> [...]  - read-only memory dump of another process."""
import ctypes, sys
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
h = k32.OpenProcess(0x0010 | 0x0400, False, int(sys.argv[1]))
if not h:
    sys.exit("OpenProcess failed: %d" % ctypes.get_last_error())
args = sys.argv[2:]
for i in range(0, len(args), 2):
    addr, size = int(args[i], 16), int(args[i + 1])
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, addr, buf, size, ctypes.byref(got))
    print("%X: %s" % (addr, buf.raw[: got.value].hex(" ") if ok else "read failed %d" % ctypes.get_last_error()))
