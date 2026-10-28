import struct, zipfile, sys, collections, glob, os
def fh3meta(d):
    # FH3 1.1 container: header 20 bytes (count u32 at +16)
    tag,maj,mi=struct.unpack_from('<4sBB',d,0)
    eo=20 if (maj,mi)==(1,1) else 16
    t,vM,vm,mc,mo,do,sz,us=struct.unpack_from('<4sBBHIIII',d,eo)
    if t!=b'BCXT': return None
    mt,sv,ro=struct.unpack_from('<4sHH',d,mo)
    m=mo+ro; a3=m+8
    w,h,dep=struct.unpack_from('<III',d,a3+16)
    arr=struct.unpack_from('<H',d,a3+28)[0]; mips=d[a3+30]; fl=d[a3+31]
    return (vM,vm),w,h,dep,arr,mips,fl
c=collections.Counter(); ex={}
files=sys.argv[1:]
for zp in files:
    try: z=zipfile.ZipFile(zp)
    except Exception: continue
    for n in z.namelist():
        if n.lower().endswith('.swatchbin'):
            r=fhm=fh3meta(z.read(n))
            if not r: c['nonBCXT']+=1; continue
            key=(r[0],r[6],r[4]&0x3fff, 'w4' if r[1]%4==0 and r[2]%4==0 else 'odd', 'mips1' if r[5]==1 else 'mips')
            c[key]+=1; ex.setdefault(key,(os.path.basename(zp),n,r))
for k,v in c.most_common(): print(v,k,ex.get(k))
