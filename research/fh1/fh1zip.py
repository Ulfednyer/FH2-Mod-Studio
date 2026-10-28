"""Forza Horizon 1 / Forza Motorsport 4 (Xbox 360) zips: entries use method 21 = XMemCompress (LZX stream, the
format quickbms' forza_horizon.bms calls XMemDecompress). Decompressed with Microsoft's xcompress64.dll (shipped
with ForzaTechStudio: ForzaTechStudio-Main\\ForzaTechStudio\\Native), CRC-checked like FTS' CustomZipFile.

Usage: py fh1zip.py list <zip>
       py fh1zip.py extract <zip> <out dir> [name filter]
Library: read(zip_path, name) -> bytes; entries(zip_path) -> [ZipInfo]
"""
import ctypes
import os
import sys
import zipfile
import zlib

DLL_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "ForzaTechStudio-Main",
                           "ForzaTechStudio", "Native", "xcompress64.dll")
_dll = None


def _xmem():
    global _dll
    if _dll is None:
        path = os.environ.get("XCOMPRESS_DLL") or os.path.normpath(DLL_DEFAULT)
        _dll = ctypes.WinDLL(path)
        _dll.XMemCreateDecompressionContext.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        _dll.XMemDecompressStream.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                              ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
        _dll.XMemDestroyDecompressionContext.argtypes = [ctypes.c_void_p]
        _dll.XMemResetDecompressionContext.argtypes = [ctypes.c_void_p]
    return _dll


def xmem_decompress(data, size):
    dll = _xmem()
    ctx = ctypes.c_void_p()
    hr = dll.XMemCreateDecompressionContext(1, None, 0, ctypes.byref(ctx))   # 1 = LZX
    if hr:
        raise RuntimeError("XMemCreateDecompressionContext 0x%08x" % (hr & 0xFFFFFFFF))
    try:
        dll.XMemResetDecompressionContext(ctx)
        out = ctypes.create_string_buffer(size)
        src = ctypes.create_string_buffer(bytes(data), len(data))
        dsize, ssize = ctypes.c_size_t(size), ctypes.c_size_t(len(data))
        hr = dll.XMemDecompressStream(ctx, out, ctypes.byref(dsize), src, ctypes.byref(ssize))
        if hr:
            raise RuntimeError("XMemDecompressStream 0x%08x" % (hr & 0xFFFFFFFF))
        return out.raw[:dsize.value]
    finally:
        dll.XMemDestroyDecompressionContext(ctx)


def entries(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return z.infolist()


def _raw(f, info):
    f.seek(info.header_offset)
    h = f.read(30)
    nlen, xlen = int.from_bytes(h[26:28], "little"), int.from_bytes(h[28:30], "little")
    f.seek(info.header_offset + 30 + nlen + xlen)
    return f.read(info.compress_size)


def read_info(zip_path, info):
    with open(zip_path, "rb") as f:
        raw = _raw(f, info)
    if info.compress_type == 0:
        data = raw
    elif info.compress_type == 8:
        data = zlib.decompress(raw, -15)
    elif info.compress_type == 21:
        data = xmem_decompress(raw, info.file_size)
    else:
        raise ValueError("compression method %d" % info.compress_type)
    if zlib.crc32(data) & 0xFFFFFFFF != info.CRC:
        raise ValueError("CRC mismatch in " + info.filename)
    return data


def read(zip_path, name):
    info = next(i for i in entries(zip_path) if i.filename.lower() == name.lower())
    return read_info(zip_path, info)


def main(argv):
    if len(argv) >= 2 and argv[0] == "list":
        for i in entries(argv[1]):
            print("%-60s m%-2d %10d" % (i.filename, i.compress_type, i.file_size))
    elif len(argv) >= 3 and argv[0] == "extract":
        flt = argv[3].lower() if len(argv) > 3 else ""
        for i in entries(argv[1]):
            if flt in i.filename.lower() and not i.is_dir():
                dst = os.path.join(argv[2], i.filename)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(read_info(argv[1], i))
                print("ok", i.filename)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
