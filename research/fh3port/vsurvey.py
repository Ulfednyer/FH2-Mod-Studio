import sys, zipfile, collections, struct
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom
def sets(d):
    try: hs, ents = geom.read_bundle(d)
    except Exception: return []
    out=[]
    for e in ents:
        if e.tag=="VLay":
            els=geom.parse_vlay(e.data)
            mask=struct.unpack_from("<I", e.data, len(e.data)-4)[0]
            out.append((tuple(sorted("%s%d"%(x["sem"][:3],x["idx"]) for x in els)), hex(mask)))
    return out
c=collections.Counter(); ex={}
for zp in sys.argv[1:]:
    z=zipfile.ZipFile(zp)
    for n in z.namelist():
        if n.lower().endswith(".modelbin"):
            for s in sets(z.read(n)):
                c[s]+=1; ex.setdefault(s,n)
for k,v in c.most_common(40): print(v,k,ex[k])
