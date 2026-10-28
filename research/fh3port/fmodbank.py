"""FMOD Studio .bank inspector: RIFF chunk tree, FSB5 sample bank (codec, samples, names).

FSB5 header: 'FSB5', u32 version, u32 numSamples, u32 sampleHeadersSize, u32 nameTableSize, u32 dataSize,
u32 mode (codec), then 8 zero, 16 hash, 8 guid (60 bytes for version 1). Sample header: u64 packed
(bit0 extra chunks, bits1-4 frequency index, bit5 stereo, bits 6-33 data offset /32 (actually <<5), bits 34-63 samples).
Codec ids (FMOD_SOUND_FORMAT): 1 PCM8 2 PCM16 3 PCM24 4 PCM32 5 PCMFLOAT 6 GCADPCM 7 IMAADPCM 8 VAG 9 HEVAG 10 XMA
11 MPEG 12 CELT 13 AT9 14 XWMA 15 VORBIS 16 FADPCM 17 OPUS.

Usage: py fmodbank.py <bank> [...]
"""
import struct
import sys

CODECS = {1: "PCM8", 2: "PCM16", 3: "PCM24", 4: "PCM32", 5: "PCMFLOAT", 6: "GCADPCM", 7: "IMAADPCM", 8: "VAG",
          9: "HEVAG", 10: "XMA", 11: "MPEG", 12: "CELT", 13: "AT9", 14: "XWMA", 15: "VORBIS", 16: "FADPCM", 17: "OPUS"}
FREQ = {1: 8000, 2: 11000, 3: 11025, 4: 16000, 5: 22050, 6: 24000, 7: 32000, 8: 44100, 9: 48000, 10: 96000}


def riff(d, o, end, depth, out):
    while o + 8 <= end:
        tag = d[o:o + 4].decode("latin-1")
        size = struct.unpack_from("<I", d, o + 4)[0]
        body = o + 8
        if tag in ("RIFF", "LIST"):
            sub = d[body:body + 4].decode("latin-1")
            out.append((depth, tag + ":" + sub, body - 8, size))
            riff(d, body + 4, body + size, depth + 1, out)
        else:
            out.append((depth, tag, body - 8, size))
        o = body + size + (size & 1)
    return out


def fsb5(d, o):
    ver, n, shs, nts, ds, mode = struct.unpack_from("<6I", d, o + 4)
    hdr = 60 if ver == 1 else 64
    p = o + hdr
    samples = []
    for i in range(n):
        v = struct.unpack_from("<Q", d, p)[0]; p += 8
        extra = v & 1
        freq = FREQ.get((v >> 1) & 0xF, (v >> 1) & 0xF)
        ch = 2 if (v >> 5) & 1 else 1
        off = ((v >> 6) & 0xFFFFFFF) * 32
        cnt = v >> 34
        chunks = []
        while extra:
            c = struct.unpack_from("<I", d, p)[0]; p += 4
            extra = c & 1
            csize = (c >> 1) & 0xFFFFFF
            ctype = c >> 25
            chunks.append((ctype, d[p:p + csize])); p += csize
        samples.append({"freq": freq, "channels": ch, "offset": off, "samples": cnt, "chunks": [(t, len(b)) for t, b in chunks]})
    names = []
    if nts:
        nt = o + hdr + shs
        offs = struct.unpack_from("<%dI" % n, d, nt)
        for k in range(n):
            s = nt + offs[k]
            names.append(d[s:d.index(b"\0", s)].decode("latin-1"))
    return {"version": ver, "count": n, "codec": CODECS.get(mode, mode), "data": ds, "samples": samples, "names": names,
            "data_at": o + hdr + shs + nts}


def inspect(path):
    d = open(path, "rb").read()
    print("==", path, len(d))
    tree = riff(d, 0, len(d), 0, [])
    for depth, tag, at, size in tree:
        if depth < 3:
            print("  " * depth + "%s @%d size %d" % (tag, at, size))
    i = d.find(b"FSB5")
    while i >= 0:
        f = fsb5(d, i)
        print("FSB5 @%d v%d %s samples=%d data=%d" % (i, f["version"], f["codec"], f["count"], f["data"]))
        for s, nm in list(zip(f["samples"], f["names"] or [""] * f["count"]))[:12]:
            print("   %-40s %dHz %dch %d samples chunks=%s" % (nm, s["freq"], s["channels"], s["samples"], s["chunks"]))
        i = d.find(b"FSB5", i + 4)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        inspect(p)
