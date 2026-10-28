import struct, zipfile, sys, collections
FMT={0:(71,72),1:(74,75),2:(77,78),3:(80,80),4:(81,81),5:(83,83),6:(84,84),7:(95,0),8:(96,0),9:(98,99),10:(2,0),11:(11,0),12:(10,0),13:(28,29),14:(85,0),15:(86,0),16:(0,0),17:(0,0),18:(0,0),19:(61,0),20:(65,0)}
def bundle(d):
    tag,maj,mi,cnt,hs,tot=struct.unpack_from('<4sBBHII',d,0)
    assert tag==b'burG' and (maj,mi)==(1,0), (tag,maj,mi)
    t,vM,vm,mc,mo,do,sz,us=struct.unpack_from('<4sBBHIIII',d,16)
    assert t==b'BCXT'
    mt,sv,ro=struct.unpack_from('<4sHH',d,mo)
    assert mt==b'HCXT'
    meta=mo+ro; msize=sv>>4
    return (vM,vm),meta,msize,do,sz
def chain(d,meta,start):
    out=[]; v=struct.unpack_from('<I',d,meta+start)[0]
    while v!=0xffffffff:
        tgt,nxt=struct.unpack_from('<II',d,meta+v); out.append((v,tgt)); v=nxt
    return out
def sim(d):
    ver,meta,msize,do,sz=bundle(d)
    base={off:tgt for off,tgt in chain(d,meta,0)}
    data={off:tgt for off,tgt in chain(d,meta,4)}
    a3=meta+8
    w,h,depth=struct.unpack_from('<III',d,a3+16)
    arr=struct.unpack_from('<H',d,a3+28)[0]&0x3fff; mips=d[a3+30]; flags=d[a3+31]
    fa,=struct.unpack_from('<i',d,a3+32); cs,=struct.unpack_from('<i',d,a3+40)
    p=base[a3+48-meta]
    fb,=struct.unpack_from('<i',d,meta+p)
    fid = fb if fa<=1 else fa
    dx = FMT.get(fid,(None,None))[1 if cs==1 else 0]
    # mip table of slice 0
    q=base.get(p+4)
    mipsz=[]
    for m in range(mips):
        size,=struct.unpack_from('<I',d,meta+q+12*m)
        mipsz.append((size,data.get(q+12*m+4)))
    return dict(ver=ver,w=w,h=h,depth=depth,arr=arr,mips=mips,flags=flags,fa=fa,cs=cs,fb=fb,dxgi=dx,blob=sz,mip0=mipsz[0] if mipsz else None,last=mipsz[-1] if mipsz else None)
if __name__=='__main__':
    stats=collections.Counter()
    for zp in sys.argv[1:]:
        z=zipfile.ZipFile(zp)
        for n in z.namelist():
            if n.lower().endswith('.swatchbin'):
                try:
                    r=sim(z.read(n)); stats[(r['fa'],r['fb'],r['cs'],r['dxgi'])]+=1
                    if r['dxgi'] in (0,None) or len(stats)<3: print(n,r)
                except Exception as e:
                    stats['ERR '+type(e).__name__]+=1; print('ERR',n,repr(e)[:120])
    print(stats)
