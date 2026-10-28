"""Lamp cover glass across FH2 cars vs the NSX: per LOD0 mesh material, BucketOrder, tris and the opacity/colour
instance parameters. usage: lampglass.py [n_cars]"""
import zipfile, struct, sys, os, re, glob, random, collections
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle, mtpr, vlayfix
import meshcheck as mc
from matidump import params
src = open(r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\ForzaTechStudio-Main\ForzaTechStudio\Services\NameHashService.cs", encoding="utf-8").read()
known = {int(h, 16): n for h, n in re.findall(r'\{\s*0x([0-9A-Fa-f]{8}),\s*"([^"]+)"\s*\}', src)}
M = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount\media\cars"
KEEP = ("Opacity", "GlassColor", "Tint", "Gloss", "F0", "Illum", "Light")


def inst(blob):
    mp, ps = None, []
    for ib in bundle.parse(blob.data):
        if ib.tag == b"ITAM":
            mp = mc.str7(ib.data, 0)[0]
        elif ib.tag == b"RPTM":
            for h, typ, v in params(ib.data):
                nm = known.get(int(h, 16), h)
                if any(k.lower() in nm.lower() for k in KEEP):
                    ps.append("%s=%s" % (nm, v))
    return mp, ps


def scan(zp):
    z = zipfile.ZipFile(zp)
    out = []
    for n in z.namelist():
        l = n.lower()
        if not l.endswith(".modelbin") or "/glass" not in l or not ("lights/" in l):
            continue
        blobs = bundle.parse(z.read(n))
        mats = {vlayfix._id(b): inst(b) for b in blobs if b.tag == b"ItaM"}
        for b in blobs:
            if b.tag != b"hseM":
                continue
            mid, bone, flags, last, first, bucket, order = struct.unpack_from("<hhHBBHB", b.data, 0)
            if mid < 0 or not flags & 1:
                continue
            mp, ps = mats.get(mid, ("?", []))
            out.append("  %-22s %-36s bucket %#x order %3d  %s" % (n.split("/")[-1][:22], (mp or "?").split("\\")[-1][:36], bucket, order, " ".join(ps)))
    return out


zips = [z for z in glob.glob(M + r"\*_*.zip") if "NSX_16" not in z and "fh3tire" not in z.lower()]
random.seed(11)
for zp in random.sample(zips, int(sys.argv[1]) if len(sys.argv) > 1 else 8) + [M + r"\ACU_NSX_16.zip"]:
    print("==", os.path.basename(zp))
    for line in scan(zp):
        print(line)
