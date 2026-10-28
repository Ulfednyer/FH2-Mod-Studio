import sys, zipfile, struct
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import mtpr, geom
z = zipfile.ZipFile(r"C:\Games\Forza Horizon 3\media\cars\ACU_NSX_16.zip")
for name in ("scene/exterior/Doors/doorHandleLF_a.modelbin",):
    d = z.read(name)
    print("==", name)
    for tag, ver, e, doff, size in mtpr.blobs(d):
        t = tag[::-1].decode("latin1")
        nmeta, moff = struct.unpack_from("<HI", d, e + 6)[0], struct.unpack_from("<I", d, e + 8)[0]
        nmeta = struct.unpack_from("<H", d, e + 6)[0]
        metas = []
        p = moff
        for _ in range(nmeta):
            mtag = d[p:p + 4][::-1].decode("latin1")
            sz_ver, rel = struct.unpack_from("<HH", d, p + 4)
            size_m = sz_ver >> 4
            val = d[p + rel:p + rel + size_m]
            metas.append((mtag, val.hex() if mtag != "Name" else val.decode("latin1", "replace")))
            p += 8
        if t == "Mesh":
            m = geom.parse_mesh(d[doff:doff + size], ver)
            tail = struct.unpack_from("<8f", d, doff + m["end"]) if size - m["end"] == 32 else None
            print("  Mesh", metas, "idxbuf", m["index_buffer"], "u316", m["u316"], "i320", m["i320"], "i324", m["i324"], "u328", m["u328"], "u332", m["u332"], "u404", m["u404"], "bind", m["bindings"], "scale/off", tuple(round(x, 4) for x in tail) if tail else None)
        elif t in ("VerB", "IndB"):
            cnt, sz, stride, nel, fmt = struct.unpack_from("<IIHHI", d, doff)
            print("  %s" % t, metas, "count", cnt, "bytes", sz, "stride", stride, "nel", nel, "fmt", fmt)
        elif t in ("VLay",):
            print("  VLay", metas)
