"""Offline test of fh2sql.dll's drift steering hook (no game needed).

Maps a fake image at 0x140000000 with what the DLL checks and patches: the 'MZ' header, the gamedb marker string, the
car builder's call at 0x141056DE3 (E8 -> 0x141061070) and a stand-in steering loader at 0x141061070 that writes FH2-like
steering values (40, 29, 90, 95, 100, 70) to car+0x5C. The call sits in a small function that sets rbp to a fake builder
frame holding the installed SpringDamper id at rbp+0x928+5*4, like sub_141056210. Then the DLL is loaded, the hook
installer patches the call, and cars with and without the drift suspension (Id % 1000 == 905) are built.

usage: py -3 -u test_drift_hook.py [path\\to\\fh2sql.dll]
"""
import ctypes
import os
import struct
import sys
import time
from ctypes import wintypes

BASE = 0x140000000
SIZE = 0x2000000
RVA_MARKER, MARKER = 0x1FF97E8, b"game:\\Media\\Stripped\\gamedbRC.slt\0"
RVA_CALL, RVA_LOADER, RVA_ENTRY = 0x1056DE3, 0x1061070, 0x1056DD9

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.VirtualAlloc.restype = ctypes.c_void_p
k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]


def put(rva, data):
    ctypes.memmove(BASE + rva, data, len(data))


def f32(v):
    return struct.pack("<f", v)


def main():
    dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "fh2sql.dll")
    p = k32.VirtualAlloc(BASE, SIZE, 0x3000, 0x40)
    if p != BASE:
        sys.exit("could not map the fake image at 0x140000000 (error %d)" % ctypes.get_last_error())
    put(0, b"MZ")
    put(RVA_MARKER, MARKER)
    # caller: push rbp; sub rsp,20h; nop; nop; mov rbp,rdx; call loader; add rsp,20h; pop rbp; ret
    rel = RVA_LOADER - (RVA_CALL + 5)
    put(RVA_ENTRY, bytes([0x55, 0x48, 0x83, 0xEC, 0x20, 0x90, 0x90, 0x48, 0x89, 0xD5]) + b"\xE8" + struct.pack("<i", rel)
        + bytes([0x48, 0x83, 0xC4, 0x20, 0x5D, 0xC3]))
    assert RVA_ENTRY + 10 == RVA_CALL
    # loader: mov dword [rcx+5Ch..70h], 40 29 90 95 100 70 ; ret
    code = b""
    for off, v in zip((0x5C, 0x60, 0x64, 0x68, 0x6C, 0x70), (40, 29, 90, 95, 100, 70)):
        code += bytes([0xC7, 0x41, off]) + f32(v)
    put(RVA_LOADER, code + b"\xC3")
    build = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)(BASE + RVA_ENTRY)

    def run(spring_id):
        car = (ctypes.c_float * 64)()
        frame = (ctypes.c_byte * 0x1000)()
        struct.pack_into("<i", frame, 0x928 + 5 * 4, spring_id)
        build(ctypes.addressof(car), ctypes.addressof(frame))
        return [round(car[0x5C // 4 + i], 2) for i in range(6)]

    print("before DLL:      ", run(441905))
    ctypes.WinDLL(dll)
    for _ in range(200):
        if ctypes.string_at(BASE + RVA_CALL + 1, 4) != struct.pack("<i", rel):
            break
        time.sleep(0.01)
    patched = struct.unpack("<i", ctypes.string_at(BASE + RVA_CALL + 1, 4))[0] != rel
    print("call patched:    ", patched)
    drift, race, stock = run(441905), run(441003), run(-1)
    print("drift suspension:", drift)
    print("race suspension: ", race)
    print("no upgrade (-1): ", stock)
    ok = patched and drift == [60, 60, 135, 142.5, 150, 105] and race == stock == [40, 29, 90, 95, 100, 70]
    # live change over the DLL's pipe (what FH2 Mod Studio sends), used for the next car built
    with open(r"\\.\pipe\fh2sql", "r+b", buffering=0) as pipe:
        req = b"#drift 45 1.2"
        pipe.write(struct.pack("<I", len(req)) + req)
        n = struct.unpack("<I", pipe.read(4))[0]
        print("pipe reply:      ", pipe.read(n).decode())
    live = run(441905)
    print("after #drift 45 1.2:", live)
    ok = ok and live == [45, 45, 108, 114, 120, 84]
    print("PASS" if ok else "FAIL")
    os._exit(0 if ok else 1)      # the DLL's pipe/file-hook threads keep running otherwise


if __name__ == "__main__":
    main()
