import zipfile, re, sys
BS = "\\"
for car, zp in [("acu_nsx_16", sys.argv[1]), ("lam_huracan_15", sys.argv[2])]:
    z = zipfile.ZipFile(zp)
    names = {n.lower() for n in z.namelist()}
    cb = z.read(next(n for n in z.namelist() if n.lower().endswith(".carbin")))
    pat = re.compile(rb"game:" + re.escape(b"\\") + rb"media" + re.escape(b"\\") + rb"cars" + re.escape(b"\\") + rb"[\x20-\x7e]+?\.(?:modelbin|swatchbin)", re.I)
    paths = sorted(set(m.decode().lower() for m in pat.findall(cb)))
    pre = "game:" + BS + "media" + BS + "cars" + BS + car + BS
    missing = [p for p in paths if p.startswith(pre) and p[len(pre):].replace(BS, "/") not in names]
    print(car, "carbin refs", len(paths), "missing", len(missing))
    for p in missing:
        print("   ", p)
    slod = [n for n in names if "__slod" in n]
    print("   __SLOD files:", len(slod), [s.split("/")[-1] for s in slod])
    print("   grille-ish refs:", [p.split(BS)[-1] for p in paths if any(k in p for k in ("honeycomb", "intercool", "grill", "mesh"))])
    unref = [n for n in names if n.endswith(".modelbin") and n.startswith("scene/") and (pre + n.replace("/", BS)) not in paths]
    print("   modelbins in zip not referenced by carbin:", len(unref), [u.split("/")[-1] for u in unref][:20])
