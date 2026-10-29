"""Cross-check every Mesh's IndB / VerB / VLay / MatI reference against the blobs of its modelbin.
py refcheck.py <car.zip> [donor.zip]"""
import collections, os, struct, sys, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fh3port"))
import bundle, geom


def bid(b):
    m = b.meta(b"  dI")
    return struct.unpack("<i", m[:4])[0] if m and len(m) >= 4 else None


def check(name, d):
    blobs = bundle.parse(d)
    tags = collections.Counter(b.tag[::-1].decode() for b in blobs)
    verb = {bid(b) for b in blobs if b.tag == b"BreV"}
    indb = {bid(b) for b in blobs if b.tag == b"BdnI"}
    nvl = tags["VLay"]
    nmat = tags["MatI"]
    probs = []
    for b in blobs:
        if b.tag != b"hseM":
            continue
        m = geom.parse_mesh(b.data, b.ver)
        mat = struct.unpack_from("<h", b.data, 0)[0]
        lid = struct.unpack_from("<i", b.data, m["bind_off"] - 8)[0]
        if m["index_buffer"] not in indb:
            probs.append("IndB %d missing" % m["index_buffer"])
        for bd in m["bindings"]:
            if bd[0] not in verb:
                probs.append("VerB %d missing" % bd[0])
        if not (0 <= lid < nvl):
            probs.append("VLay idx %d of %d" % (lid, nvl))
        if not (-1 <= mat < nmat):
            probs.append("MatI %d of %d" % (mat, nmat))
        if m["end"] != len(b.data):
            probs.append("mesh %s len %d parsed %d" % (b.ver, len(b.data), m["end"]))
    return dict(tags), sorted(verb), sorted(indb), probs


for zp in sys.argv[1:]:
    z = zipfile.ZipFile(zp)
    print("==", zp)
    bad = 0
    for n in z.namelist():
        if not n.lower().endswith(".modelbin"):
            continue
        d = z.read(n)
        try:
            tags, verb, indb, probs = check(n, d)
        except Exception as e:
            print("  ERR", n, e); bad += 1; continue
        if probs or "-v" in sys.argv:
            bad += bool(probs)
            print("  %s %s verb=%s indb=%s %s" % (n, tags, verb, indb, sorted(set(probs))))
    print("  models with problems:", bad)
