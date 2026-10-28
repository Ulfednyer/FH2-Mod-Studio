"""Fill empty carbin AO maps with a white (no occlusion) AO texture.

FH2 gives every main lamp model a per-model AO map (carbin AOMapInfo path; only bulbs, lenses and the interior LOD go
without). FH3 does too, except some cars - the FH3 NSX has EMPTY AO entries for headlightL/R, taillightL/R/C,
taillightCHMSL and doorHandleRF (it lights its lamps through textures/lp/*_radiosity instead). FH2's
CarRenderModel11::off10_vf07 (0x1411BF8A0) only loads an AO texture when the path is non-empty and otherwise leaves the
slot null; those models render black in FH2 whatever their material.

The white AO is built from one of the car's own BC4 AO swatchbins (FH2 already loads those): same header, every
8-byte BC4 block set to "255, 255, indices 0" (= 1.0 at every mip), fresh texture GUID.
"""
import os
import struct
import uuid
import zipfile

import bundle
import carbin
import tex
import ziputil

WHITE_NAME = "Textures/ao/fh2port_white_ao.swatchbin"
SKIP = ("bulbs", "glass", "lens", "interior_a", "__slod")


def make_white(template):
    lay = tex._layout(template)
    if not lay or lay[1] == (2, 0) or tex._dxgi(template, lay[0]) != 80:
        raise ValueError("template is not a PC BC4 texture")
    meta = lay[0]
    blobs = bundle.parse(template)
    for b in blobs:
        if b.tag == b"BCXT":
            if len(b.data) % 8:
                raise ValueError("BC4 data not a whole number of blocks")
            b.data = b"\xff\xff\x00\x00\x00\x00\x00\x00" * (len(b.data) // 8)
            b.usize = len(b.data)
            # fresh GUID in the texture header (header + 8, 16 bytes) so it can't alias the template texture
            md = [list(m) for m in b.metas]
            for m in md:
                if m[0] == b"HCXT":
                    h = bytearray(m[2])
                    h[8:24] = uuid.uuid4().bytes_le
                    m[2] = bytes(h)
            b.metas = [tuple(m) for m in md]
    return bundle.serialize(blobs)


def fix_zip(src, dst, car_name):
    log = []
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        low = {n.lower(): n for n in names}
        cb_name = next((n for n in names if n.lower().endswith(".carbin")), None)
        templates = []
        for n in names:
            l = n.lower()
            if "/ao/" in l and l.endswith(".swatchbin"):
                d = zin.read(n)
                lay = tex._layout(d)
                if lay and lay[1] != (2, 0) and tex._dxgi(d, lay[0]) == 80:
                    templates.append((len(d), n))
        if not cb_name or not templates:
            log.append("no carbin or no BC4 AO template - skipped")
            with ziputil.writer(dst) as zout:
                for info in zin.infolist():
                    zout.writestr(info.filename, zin.read(info))
            return log
        cb = zin.read(cb_name)
        r = carbin.parse(cb)
        white_path = "game:\\media\\cars\\%s\\%s" % (car_name.lower(), WHITE_NAME.replace("/", "\\").lower())
        changes = {}
        for off, model_path, ao_path in r.ao_paths:
            m = model_path.split("\\")[-1].lower()
            rel = model_path.lower().split("\\%s\\" % car_name.lower(), 1)[-1].replace("\\", "/")
            if ao_path or any(k in m for k in SKIP) or rel not in low:
                continue
            changes[off] = white_path
            log.append("%s: empty AO -> white" % m)
        with ziputil.writer(dst) as zout:
            for info in zin.infolist():
                data = zin.read(info)
                if info.filename == cb_name and changes:
                    data = carbin.set_ao_paths(data, changes)
                zout.writestr(info.filename, data)
            if changes and WHITE_NAME.lower() not in low:
                zout.writestr(WHITE_NAME, make_white(zin.read(sorted(templates)[0][1])))
    return log
