"""Learn FH3 -> FH2 material conversion from the two games' libraries.

Many library materials exist in both games under the same name (interiorengine/leather_lgl ...). For FH3 shaders FH2
lacks, those pairs show which FH2 shader the same surface uses, and which FH2 parameter carries each FH3 value.

    py matlearn.py <fh3 Materials.zip> <fh2 Materials.zip> <fh2 Shaders.zip> [out.json]
"""
import json
import os
import struct
import sys
import zipfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fh3port"))
import mtpr  # noqa: E402
from lightparams import NAMES, _s7  # noqa: E402


def material(data):
    """(shader base name, {hash: (type, value)}) of a materialbin (FH2 1.0 or FH3 1.1 bundle)."""
    shader, params = None, {}
    for tag, ver, _, doff, size in mtpr.blobs(data):
        if tag[::-1] == b"MATL":
            shader = _s7(data, doff)[0].replace("\\", "/").rsplit("/", 1)[-1].lower().replace(".shaderbin", "")
        elif tag == b"RPTM":
            b = data[doff:doff + size]
            try:
                ps, _ = mtpr.parse_params(b, ver)
            except mtpr.ParseError:
                continue
            for start, stop, maj, mn, h, typ in ps:
                p = start + 6 + (5 if (maj, mn) >= (3, 1) and b[start + 6] else (1 if (maj, mn) >= (3, 1) else 0))
                p += 1 + (16 if maj >= 3 else 0)
                params[h] = (typ, value(b, p, typ))
    return shader, params


def value(b, p, typ):
    if typ in (0, 1, 5, 9):
        return [round(x, 4) for x in struct.unpack_from("<4f", b, p)]
    if typ == 2:
        return round(struct.unpack_from("<f", b, p)[0], 4)
    if typ in (3, 4):
        return struct.unpack_from("<i", b, p)[0]
    if typ == 11:
        return [round(x, 4) for x in struct.unpack_from("<2f", b, p)]
    if typ == 6:
        s, _ = _s7(b, p)
        return s.replace("\\", "/").rsplit("/", 1)[-1].lower().split("_", 1)[-1] if False else \
            s.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return None


def load(zp):
    out = {}
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            if n.lower().endswith(".materialbin"):
                try:
                    out[n.lower()] = material(z.read(n))
                except Exception:
                    pass
    return out


def tex_key(v):
    """Texture file name without the trailing GUID / swatch suffix, for matching across games."""
    v = v.rsplit(".", 1)[0]
    parts = v.split("_")
    while parts and len(parts[-1]) in (8, 4, 12) and all(c in "0123456789abcdef-" for c in parts[-1]):
        parts.pop()
    return "_".join(parts)


def main(fh3_zip, fh2_zip, shaders_zip, out=None):
    m3, m2 = load(fh3_zip), load(fh2_zip)
    with zipfile.ZipFile(shaders_zip) as z:
        fh2_shaders = {n.lower().rsplit("/", 1)[-1].replace(".shaderbin", "") for n in z.namelist()}
    by_base2 = defaultdict(list)
    for n in m2:
        by_base2[n.rsplit("/", 1)[-1]].append(n)
    pairs = defaultdict(list)                        # fh3 shader -> [(fh3 name, fh2 name)]
    for n, (s3, _) in m3.items():
        if s3 and s3 not in fh2_shaders:
            for n2 in by_base2.get(n.rsplit("/", 1)[-1], []):
                pairs[s3].append((n, n2))
    usage = Counter(s for s, _ in m3.values() if s and s not in fh2_shaders)
    result = {}
    for s3, cnt in usage.most_common():
        sh2 = Counter(m2[b][0] for _, b in pairs[s3])
        corr = defaultdict(Counter)                   # fh3 param -> Counter(fh2 param) by equal value
        for a, b in pairs[s3]:
            p3, p2 = m3[a][1], m2[b][1]
            for h3, (t3, v3) in p3.items():
                for h2, (t2, v2) in p2.items():
                    if t3 != t2:
                        continue
                    same = (tex_key(v3) == tex_key(v2)) if t3 == 6 else (v3 == v2 and v3 not in (0, 1, 0.0, 1.0)
                                                                         and v3 != [0, 0, 0, 0] and v3 != [1, 1, 1, 1])
                    if same:
                        corr[NAMES.get(h3, hex(h3))][NAMES.get(h2, hex(h2))] += 1
        result[s3] = {"materials": cnt, "pairs": len(pairs[s3]), "fh2_shaders": sh2.most_common(6),
                      "params": {k: v.most_common(3) for k, v in sorted(corr.items())}}
    txt = json.dumps(result, indent=1)
    if out:
        open(out, "w").write(txt)
    for s3, r in result.items():
        print("%-45s %4d mats %4d pairs  %s" % (s3, r["materials"], r["pairs"], r["fh2_shaders"][:3]))


if __name__ == "__main__":
    main(*sys.argv[1:])
