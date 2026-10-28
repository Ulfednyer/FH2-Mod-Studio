import struct,zipfile,glob,sys
def parse(d):
    p=0
    def u32():
        nonlocal p; v=struct.unpack_from('<I',d,p)[0]; p+=4; return v
    m=u32(); assert m==0xDEADBEEF
    ver=u32()
    for _ in range(u32()):
        n=u32(); p+=n+2
    nl=u32(); p+=76*nl
    no=u32(); p+=72*no
    return ver,nl,no,len(d)-p
for root in sys.argv[1:]:
    ok=bad=0
    for z in glob.glob(root+'/*.zip'):
        try: zz=zipfile.ZipFile(z)
        except Exception: continue
        for n in zz.namelist():
            if n.lower()=='lights.bin':
                r=parse(zz.read(n))
                if r[3]==0: ok+=1
                else: bad+=1; print(z,r) if bad<5 else None
    print(root,'ok',ok,'bad',bad)
