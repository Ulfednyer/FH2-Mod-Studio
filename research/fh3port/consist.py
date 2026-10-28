import sys, zipfile, struct
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import geom
bad=0; n_models=0
z=zipfile.ZipFile(sys.argv[1])
for n in z.namelist():
    if not n.lower().endswith(".modelbin"): continue
    d=z.read(n); hs,ents=geom.read_bundle(d); n_models+=1
    slots=[]
    for e in ents:
        if e.tag=="VLay":
            els=geom.parse_vlay(e.data)
            for s in sorted({x["slot"] for x in els}):
                se=[x for x in els if x["slot"]==s]
                slots.append((len(se), se[0]["fmt"], sum(geom.DXGI_SIZE[x["fmt"]] for x in se)))
    strides={}
    for e in ents:
        if e.tag=="VerB":
            cnt,sz,stride,nel,fmt=struct.unpack_from("<IIHHI",e.data,0)
            strides[geom.blob_id(e)]=stride
            if sz!=cnt*stride or len(e.data)<16+sz or (nel,fmt,stride) not in slots:
                bad+=1; print("VerB mismatch",n,geom.blob_id(e),(nel,fmt,stride),slots[:4])
    for e in ents:
        if e.tag=="Mesh":
            m=geom.parse_mesh(e.data,e.ver)
            for bid,slot,st,off in m["bindings"]:
                if bid in strides and st and st!=strides[bid]:
                    bad+=1; print("binding stride",n,bid,st,strides[bid])
print("models",n_models,"problems",bad)
