"""
FH1 -> FH2 Automated Car Porting Pipeline.
Ports cars from Forza Horizon 1 (Xbox 360) into Forza Horizon 2 (Xbox One / Azimuth PC).

Usage:
    python fh1port.py port <FH1_CAR> <DONOR_CAR> [--id <NEW_ID>]
    python fh1port.py check <CAR_MEDIA_NAME>
"""

import argparse
import os
import re
import shutil
import sqlite3
import struct
import sys
import zipfile
import zlib
from datetime import datetime

# Setup search paths
HERE = os.path.dirname(os.path.abspath(__file__))
FH3PORT = os.path.normpath(os.path.join(HERE, "..", "..", "fh3port"))
if FH3PORT not in sys.path:
    sys.path.insert(0, FH3PORT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bundle
import carbin as scene_carbin
import fh1zip
import fh1carbin
import fh1modelbin
import swatch
import xds
import strtables
import geom
import fh3port

# Default Paths
FH1_DEFAULT_ROOT = r"D:\Xbox\Forza\fh1debug new extract"
GAME_DEFAULT_ROOT = r"c:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe"

LANGS = ["br", "CHT", "cz", "DE", "DEV", "EN", "ES", "FR", "GB", "HU", "IT", "JP", "KO", "LOC", "MX", "nl", "PL", "RU"]


def rename_scene(data: bytes, new_car_id: int, old_media: str, new_media: str) -> bytes:
    """Recursively rewrites an FH2 scene carbin replacing carId and media paths."""
    old_m_lower = old_media.lower()
    new_m_lower = new_media.lower()

    r = scene_carbin.Reader(data)
    out = bytearray()

    ver = r.u16()
    out += struct.pack("<H", ver)
    out += r.take(16)  # guid16
    out += r.take(1)   # u8
    old_cid = r.u32()
    out += struct.pack("<I", new_car_id)

    def copy_str():
        nonlocal out
        s = r.s()
        # shared files (game:\media\cars\_library\..., e.g. the donor's wheel AO in Textures.zip) keep the donor's
        # name - renamed, they pointed at files that don't exist and the showroom 3D view stayed black
        if "\\cars\\_library\\" in s.lower():
            s_new = s
        else:
            s_new = s.replace(old_m_lower, new_m_lower).replace(old_media, new_media)
        s_bytes = s_new.encode("latin-1")
        out += struct.pack("<I", len(s_bytes)) + s_bytes
        return s_new

    copy_str()  # name
    copy_str()  # skel

    if ver >= 2:
        out += r.take(2)  # lodMask

    def copy_model():
        nonlocal out
        mv = r.u16()
        out += struct.pack("<H", mv)
        copy_str()  # path
        out += r.take(64)  # mat4
        if mv < 5:
            out += r.take(4)
        else:
            out += r.take(2)  # lodMask
        copy_str()  # parent
        out += r.take(7)  # u16, u8, u32
        if mv < 9:
            copy_str()
        if mv >= 2:
            n = r.count()
            out += struct.pack("<I", n)
            for _ in range(n):
                copy_str()
                k = r.count()
                out += struct.pack("<I", k) + r.take(k)
        if mv >= 3:
            n = r.count()
            out += struct.pack("<I", n)
            for _ in range(n):
                copy_str()
                out += r.take(4)
        if mv >= 6:
            drop = r.u8()
            out += struct.pack("<B", drop)
            if drop:
                out += r.take(8)
        if mv >= 8:
            out += r.take(4)
        if mv >= 9:
            n = r.count()
            out += struct.pack("<I", n)
            for _ in range(n):
                aov = r.u16()
                out += struct.pack("<H", aov)
                copy_str()
                out += r.take(8)
                if aov == 1:
                    out += r.take(3)
                elif aov >= 2:
                    out += r.take(16)
                out += r.take(1)
                if aov >= 3:
                    out += r.take(2)
        if mv >= 10:
            out += r.take(1)
        if mv >= 11:
            out += r.take(18)
        if mv >= 12:
            copy_str()
        if mv >= 13:
            out += r.take(16)
        if mv >= 14:
            out += r.take(20)
        if mv >= 15:
            out += r.take(4)

    def copy_part():
        nonlocal out
        pv = r.u16()
        out += struct.pack("<H", pv)
        out += r.take(4)  # id
        nm = r.count()
        out += struct.pack("<I", nm)
        for _ in range(nm):
            copy_model()
        if pv >= 2:
            out += r.take(32)

    # Parts
    np_cnt = r.count()
    out += struct.pack("<I", np_cnt)
    for _ in range(np_cnt):
        if ver >= 4:
            out += r.take(1)  # type
        copy_part()

    # UpgradableParts
    nup = r.count()
    out += struct.pack("<I", nup)
    for _ in range(nup):
        upv = r.u16()
        out += struct.pack("<H", upv)
        out += r.take(4)  # id
        n_upg = r.count()
        out += struct.pack("<I", n_upg)
        for _ in range(n_upg):
            uv = r.u16()
            out += struct.pack("<H", uv)
            out += r.take(11)
            if uv < 3:
                nm = r.count()
                out += struct.pack("<I", nm)
                for _ in range(nm):
                    copy_model()
            if uv >= 2:
                out += r.take(32)
        if upv >= 3:
            n_extra = r.count()
            out += struct.pack("<I", n_extra)
            for _ in range(n_extra):
                k = r.count()
                out += struct.pack("<I", k) + r.take(k * 4)
                copy_model()

    if r.p < len(r.d):
        out += r.take(len(r.d) - r.p)

    return bytes(out)


def rewrite_lights_bin(data: bytes, old_media: str, new_media: str) -> bytes:
    """Updates length-prefixed model paths in Lights.bin."""
    old_b = old_media.lower().encode("latin1")
    new_b = new_media.lower().encode("latin1")
    buf = bytearray(data)

    p = 0
    while p + 4 < len(buf):
        slen = struct.unpack_from("<I", buf, p)[0]
        if 10 < slen < 500 and p + 4 + slen <= len(buf):
            s = bytes(buf[p+4:p+4+slen])
            if s.startswith(b"game:\\media\\cars\\") and old_b in s:
                s_new = s.replace(old_b, new_b)
                buf[p:p+4+slen] = struct.pack("<I", len(s_new)) + s_new
                p += 4 + len(s_new)
                continue
        p += 1
    return bytes(buf)


def parse_lsb2_be(d: bytes):
    """Parses an Xbox 360 big-endian LSB2 string table."""
    endian = ">" if (d[4] & 1) else "<"
    encoding = "utf-16-be" if (d[4] & 1) else "utf-16-le"

    sec0 = struct.unpack_from(endian + "I", d, 12)[0]
    n = struct.unpack_from(endian + "I", d, 16)[0]
    size, count = struct.unpack_from(endian + "II", d, sec0)

    ents = [struct.unpack_from(endian + "HI", d, sec0 + 8 + 6 * i) for i in range(count + 1)]
    pool = sec0 + 8 + 6 * (count + 1)

    strings = {}
    for k, o in ents[:-1]:
        p = pool + 2 * o
        e = p
        while e + 1 < len(d) and (d[e] or d[e + 1]):
            e += 2
        strings[k] = d[p:e].decode(encoding, "replace")
    return strings


def build_car_archive(fh1_zip_path: str, donor_zip_path: str, out_zip_path: str,
                       fh1_car_name: str, donor_car_name: str, new_car_id: int):
    """Builds a complete FH2 car zip by merging FH1 geometry into donor zip structure."""
    print(f"\n[1/4] Building car archive: {out_zip_path}")
    print(f"      FH1 Source: {fh1_zip_path}")
    print(f"      Donor Source: {donor_zip_path}")

    # Load FH1 geometry
    lod0_data = fh1zip.read(fh1_zip_path, f"{fh1_car_name}_lod0.carbin")
    m_lod0 = fh1carbin.FH1Carbin.load(lod0_data)

    cockpit_data = fh1zip.read(fh1_zip_path, f"{fh1_car_name}_cockpit.carbin")
    m_cockpit = fh1carbin.FH1Carbin.load(cockpit_data)

    # Read donor skeleton from body modelbin
    with zipfile.ZipFile(donor_zip_path) as zd:
        donor_body_bytes = zd.read("scene/_library/scene/R8/Scene/Exterior/Platform/body_a.modelbin")
        donor_blobs = bundle.parse(donor_body_bytes)
        skel_blob = next((b for b in donor_blobs if b.tag[::-1] == b"Skel"), None)

    # Map of FH2 modelbin path -> FH1 Part(s)
    modelbin_replacements = {}

    def add_rep(pname: str, model_rel_path: str, source_model=m_lod0):
        if pname in source_model.parts:
            part = source_model.parts[pname]
            mb = fh1modelbin.convert_part_to_modelbin(part, skel_blob)
            modelbin_replacements[model_rel_path.lower()] = mb
            print(f"      Converted part '{pname:15s}' -> {model_rel_path} ({len(mb):,} bytes)")

    add_rep("body", "scene/_library/scene/R8/Scene/Exterior/Platform/body_a.modelbin", m_lod0)
    add_rep("bumperFa", "scene/Exterior/BumperF/bumperF_a.modelbin", m_lod0)
    add_rep("bumperFrace", "scene/Exterior/BumperF/bumperF_race.modelbin", m_lod0)
    add_rep("bumperRa", "scene/Exterior/BumperR/bumperR_a.modelbin", m_lod0)
    add_rep("winga", "scene/_library/scene/R8/Scene/Exterior/Trunk/wing_a.modelbin", m_lod0)
    add_rep("wingrace", "scene/_library/scene/R8/Scene/Exterior/Trunk/wing_race.modelbin", m_lod0)
    # Combined skirts (skirtLa + skirtRa)
    if "skirtLa" in m_lod0.parts and "skirtRa" in m_lod0.parts:
        comb_sk = fh1modelbin.combine_parts([m_lod0.parts["skirtLa"], m_lod0.parts["skirtRa"]], "skirt_a")
        mb_sk = fh1modelbin.convert_part_to_modelbin(comb_sk, skel_blob)
        modelbin_replacements["scene/_library/scene/r8/scene/exterior/sideskirts/skirtl_a.modelbin"] = mb_sk
        print(f"      Converted combined skirts -> scene/_library/scene/R8/Scene/Exterior/SideSkirts/skirtL_a.modelbin ({len(mb_sk):,} bytes)")
    else:
        add_rep("skirtLa", "scene/_library/scene/R8/Scene/Exterior/SideSkirts/skirtL_a.modelbin", m_lod0)
    add_rep("trunk", "scene/_library/scene/R8/Scene/Exterior/Trunk/trunk_a.modelbin", m_lod0)
    add_rep("undercarriagea", "scene/Exterior/Chassis/Undercarriage_a.modelbin", m_lod0)

    # Combined exhaust
    if "exhaustLa" in m_lod0.parts and "exhaustRa" in m_lod0.parts:
        comb_ex = fh1modelbin.combine_parts([m_lod0.parts["exhaustLa"], m_lod0.parts["exhaustRa"]], "exhaust_a")
        mb_ex = fh1modelbin.convert_part_to_modelbin(comb_ex, skel_blob)
        modelbin_replacements["scene/exterior/chassis/exhaust_a.modelbin"] = mb_ex
        print(f"      Converted combined exhaust -> scene/Exterior/Chassis/exhaust_a.modelbin ({len(mb_ex):,} bytes)")

    add_rep("glassF", "scene/_library/scene/R8/Scene/Exterior/Windows/glassF_a.modelbin", m_lod0)
    add_rep("glassR", "scene/_library/scene/R8/Scene/Exterior/Windows/glassR_a.modelbin", m_lod0)
    add_rep("glassLF", "scene/_library/scene/R8/Scene/Exterior/Windows/glassLF.modelbin", m_lod0)
    add_rep("glassRF", "scene/_library/scene/R8/Scene/Exterior/Windows/glassRF.modelbin", m_lod0)
    add_rep("glassLR", "scene/_library/scene/R8/Scene/Exterior/Windows/glassLR_a.modelbin", m_lod0)
    add_rep("glassRR", "scene/_library/scene/R8/Scene/Exterior/Windows/glassRR_a.modelbin", m_lod0)
    add_rep("headlightL", "scene/Exterior/PrimaryLights/headlightL_a.modelbin", m_lod0)
    add_rep("headlightR", "scene/Exterior/PrimaryLights/headlightR_a.modelbin", m_lod0)
    add_rep("glassLHL", "scene/Exterior/PrimaryLights/glassLHL_a.modelbin", m_lod0)
    add_rep("glassRHL", "scene/Exterior/PrimaryLights/glassRHL_a.modelbin", m_lod0)
    add_rep("taillightL", "scene/Exterior/SecondaryLights/taillightL_a.modelbin", m_lod0)
    add_rep("taillightR", "scene/Exterior/SecondaryLights/taillightR_a.modelbin", m_lod0)
    add_rep("glassLTL", "scene/Exterior/SecondaryLights/glassLTL_a.modelbin", m_lod0)
    add_rep("glassRTL", "scene/Exterior/SecondaryLights/glassRTL_a.modelbin", m_lod0)
    add_rep("wheel", f"scene/_library/scene/Wheels/{donor_car_name}_wheelLF.modelbin", m_lod0)

    # Cockpit parts
    add_rep("hooda", "scene/_library/scene/R8/Scene/Exterior/Hood/hood_a.modelbin", m_cockpit)
    add_rep("interior", "scene/_library/scene/R8/Scene/Interior/InteriorLOD/Interior_a.modelbin", m_cockpit)
    add_rep("cagerace", "scene/_library/scene/R8/Scene/Interior/Floor/rollCage_a.modelbin", m_cockpit)

    # Convert all XDS textures from FH1 car zip
    xds_swatches = {}
    for entry in fh1zip.entries(fh1_zip_path):
        if entry.filename.lower().endswith(".xds"):
            try:
                raw_xds = fh1zip.read_info(fh1_zip_path, entry)
                x = xds.Xds(raw_xds)
                sw_bytes = swatch.from_xds(x, entry.filename)
                # target swatch name
                stem = os.path.splitext(entry.filename)[0]
                target_name = f"Textures/{stem}.swatchbin"
                xds_swatches[target_name.lower()] = (target_name, sw_bytes)
                print(f"      Converted texture '{entry.filename}' -> {target_name} ({len(sw_bytes):,} bytes)")
            except Exception as e:
                print(f"      Warning: could not convert texture {entry.filename}: {e}")

    # Build final archive
    out_entries = []
    with zipfile.ZipFile(donor_zip_path) as zd:
        for info in zd.infolist():
            name = info.filename
            data = zd.read(info)
            name_lower = name.lower()

            # 1) Scene carbin
            if name_lower == f"{donor_car_name.lower()}.carbin":
                new_scene_bytes = rename_scene(data, new_car_id, donor_car_name, fh1_car_name)
                out_name = f"{fh1_car_name}.carbin"
                out_entries.append(fh3port._entry_from_bytes(out_name, new_scene_bytes))
                print(f"      Wrote renamed scene carbin: {out_name}")
                continue

            # 2) Lights.bin
            if name_lower == "lights.bin":
                new_lights_bytes = rewrite_lights_bin(data, donor_car_name, fh1_car_name)
                out_entries.append(fh3port._entry_from_bytes(name, new_lights_bytes))
                print(f"      Wrote updated Lights.bin")
                continue

            # 3) Replaced modelbins
            if name_lower in modelbin_replacements:
                new_model_bytes = modelbin_replacements[name_lower]
                out_name = name.replace(donor_car_name, fh1_car_name)
                out_entries.append(fh3port._entry_from_bytes(out_name, new_model_bytes))
                continue

            # 4) Renamed donor files
            out_name = name.replace(donor_car_name, fh1_car_name)
            out_entries.append(fh3port._entry_from_bytes(out_name, data))

    # Add converted swatches
    for target_lower, (target_name, sw_bytes) in xds_swatches.items():
        out_entries.append(fh3port._entry_from_bytes(target_name, sw_bytes))

    # Write native FH2 zip file
    fh3port.write_native_zip(out_zip_path, out_entries)
    # vertex layouts to exactly what each mesh's FH2 shader takes (the generic main layout supplied extra or missing
    # inputs: Azimuth D3D12 pipeline errors / black parts, see fh3port vlayfix + CRASHES.md)
    tmp = out_zip_path + ".vlay.zip"
    log = fh3port.fix_vertex_layouts(out_zip_path, tmp, fh1_car_name)
    fh3port.normalize_zip(tmp, out_zip_path)
    os.remove(tmp)
    print(f"      Successfully wrote {out_zip_path} with {len(out_entries)} entries ({len(log)} vertex layout fixes).")


def inject_database(fh1_db_path: str, fh2_db_path: str, fh1_car_name: str, donor_car_name: str,
                    new_car_id: int, fh1_car_id: int = 1551, donor_car_id: int = 2010):
    """Injects FH1 car physics, dimensions, and cloned upgrades into FH2 database."""
    print(f"\n[2/4] Injecting car into database: {fh2_db_path}")

    db1 = sqlite3.connect(fh1_db_path)
    db1.row_factory = sqlite3.Row

    db2 = sqlite3.connect(fh2_db_path)
    db2.row_factory = sqlite3.Row

    # 1) Data_Car
    r1 = db1.execute("SELECT * FROM Data_Car WHERE Id = ?", (fh1_car_id,)).fetchone()
    r2 = db2.execute("SELECT * FROM Data_Car WHERE Id = ?", (donor_car_id,)).fetchone()

    cols2 = [c[1] for c in db2.execute("PRAGMA table_info('Data_Car')")]
    new_car_row = {}

    for c in cols2:
        if c in r1.keys() and r1[c] is not None:
            new_car_row[c] = r1[c]
        elif c in r2.keys():
            new_car_row[c] = r2[c]
        else:
            new_car_row[c] = 0

    # Overrides for ported car
    new_car_row["Id"] = new_car_id
    new_car_row["ModelId"] = new_car_id
    new_car_row["MediaName"] = fh1_car_name
    new_car_row["DisplayName"] = f"_&{(0xCD49 << 16) | 22844}"
    new_car_row["ModelShort"] = f"_&{(0xCD49 << 16) | 24312}"
    new_car_row["ContentId"] = 0
    new_car_row["IsPurchased"] = 1
    new_car_row["IsInstalled"] = 1
    new_car_row["IsDrivable"] = 1
    new_car_row["IsArcade"] = 0
    new_car_row["Thumbnail"] = f"game:\\Media\\Stripped\\RC0\\Thumbnail_{donor_car_id}.png"
    new_car_row["StockWheelID"] = r2["StockWheelID"]
    new_car_row["IsOpenCockpit"] = 0
    new_car_row["IsOpenWheel"] = 0

    # Clean existing
    db2.execute("DELETE FROM Data_Car WHERE Id = ?", (new_car_id,))
    col_str = ", ".join(f'"{c}"' for c in cols2)
    val_str = ", ".join("?" for _ in cols2)
    db2.execute(f"INSERT INTO Data_Car ({col_str}) VALUES ({val_str})", [new_car_row[c] for c in cols2])
    print(f"      Inserted Data_Car row for {fh1_car_name} (Id={new_car_id})")

    # 1b) Data_Car_Buckets (mandatory for autoshow / purchase transactions)
    db2.execute("DELETE FROM Data_Car_Buckets WHERE CarId = ?", (new_car_id,))
    donor_bucket = db2.execute("SELECT CarBucket, BucketHero FROM Data_Car_Buckets WHERE CarId = ?", (donor_car_id,)).fetchone()
    if donor_bucket:
        db2.execute("INSERT INTO Data_Car_Buckets (CarId, CarBucket, BucketHero) VALUES (?, ?, ?)",
                    (new_car_id, donor_bucket["CarBucket"], donor_bucket["BucketHero"]))
        print(f"      Inserted Data_Car_Buckets: CarBucket={donor_bucket['CarBucket']}, BucketHero={donor_bucket['BucketHero']}")

    # 2) CameraOverrides
    db2.execute("DELETE FROM CameraOverrides WHERE CarId = ?", (new_car_id,))
    cam1 = db1.execute("SELECT * FROM CameraOverrides WHERE CarId = ?", (fh1_car_id,)).fetchone()
    if cam1:
        cols_cam = [c[1] for c in db2.execute("PRAGMA table_info('CameraOverrides')")]
        cam_row = {c: cam1[c] if c in cam1.keys() else 0.0 for c in cols_cam}
        cam_row["CarId"] = new_car_id
        c_str = ", ".join(f'"{c}"' for c in cols_cam)
        v_str = ", ".join("?" for _ in cols_cam)
        db2.execute(f"INSERT INTO CameraOverrides ({c_str}) VALUES ({v_str})", [cam_row[c] for c in cols_cam])
        print(f"      Inserted CameraOverrides for CarId={new_car_id}")

    # 3) CarPartPositions (modern FH2 Durango standard: single root locator row)
    db2.execute("DELETE FROM CarPartPositions WHERE Ordinal = ?", (new_car_id,))
    db2.execute("INSERT INTO CarPartPositions (ID, Ordinal, PartId, PartPosX, PartPosY, PartPosZ) VALUES (?, ?, 0, 0.0, 0.0, 0.0)",
                (new_car_id * 1000, new_car_id))
    print(f"      Inserted CarPartPositions locator for Ordinal={new_car_id}")

    # 4) Combo_Colors
    db2.execute("DELETE FROM Combo_Colors WHERE Ordinal = ?", (new_car_id,))
    for col in db1.execute("SELECT * FROM Combo_Colors WHERE Ordinal = ?", (fh1_car_id,)):
        c_row = dict(col)
        c_row["Ordinal"] = new_car_id
        c_row["ID"] = new_car_id * 1000 + c_row["Sequence"]
        cols_c = list(c_row.keys())
        db2.execute(f"INSERT INTO Combo_Colors ({', '.join(cols_c)}) VALUES ({', '.join('?' * len(cols_c))})", list(c_row.values()))
    print(f"      Inserted Combo_Colors for Ordinal={new_car_id}")

    # 5) Data_CarBody
    db2.execute("DELETE FROM Data_CarBody WHERE Id = ?", (new_car_id * 1000,))
    cb1 = db1.execute("SELECT * FROM Data_CarBody WHERE Id = ?", (fh1_car_id * 1000,)).fetchone()
    cb2 = db2.execute("SELECT * FROM Data_CarBody WHERE Id = ?", (donor_car_id * 1000,)).fetchone()
    cols_cb2 = [c[1] for c in db2.execute("PRAGMA table_info('Data_CarBody')")]
    cb_row = {}
    for c in cols_cb2:
        if cb1 and c in cb1.keys() and cb1[c] is not None:
            cb_row[c] = cb1[c]
        elif cb2 and c in cb2.keys():
            cb_row[c] = cb2[c]
        else:
            cb_row[c] = 0.0
    cb_row["Id"] = new_car_id * 1000
    db2.execute(f"INSERT INTO Data_CarBody ({', '.join(cols_cb2)}) VALUES ({', '.join('?' * len(cols_cb2))})", [cb_row[c] for c in cols_cb2])
    print(f"      Inserted Data_CarBody for Id={new_car_id * 1000}")

    # 5b) Clone all body-keyed upgrade tables (CarBodyID = donor_car_id * 1000 -> new_car_id * 1000)
    body_upgrade_tables = [
        "List_UpgradeCarBody",
        "List_UpgradeCarBodyChassisStiffness",
        "List_UpgradeCarBodyFrontBumper",
        "List_UpgradeCarBodyHood",
        "List_UpgradeCarBodyRearBumper",
        "List_UpgradeCarBodySideSkirt",
        "List_UpgradeCarBodyTireWidthFront",
        "List_UpgradeCarBodyTireWidthRear",
        "List_UpgradeCarBodyWeight"
    ]
    old_body = donor_car_id * 1000
    new_body = new_car_id * 1000
    for bt in body_upgrade_tables:
        cols_bt = [c[1] for c in db2.execute(f"PRAGMA table_info('{bt}')").fetchall()]
        cb_col = next((c for c in cols_bt if "carbody" in c.lower()), "CarBodyID")
        db2.execute(f"DELETE FROM {bt} WHERE {cb_col} = ?", (new_body,))
        if "Id" in cols_bt:
            db2.execute(f"DELETE FROM {bt} WHERE Id >= ? AND Id < ?", (new_body, new_body + 1000))
        donor_rows = db2.execute(f"SELECT * FROM {bt} WHERE {cb_col} = ?", (old_body,)).fetchall()
        for dr in donor_rows:
            r_dict = dict(dr)
            for k in list(r_dict.keys()):
                if k.lower() == "carbodyid":
                    r_dict[k] = new_body
                elif k.lower() == "ordinal":
                    r_dict[k] = new_car_id
                elif k.lower() == "id" and isinstance(r_dict[k], int):
                    if old_body <= r_dict[k] < old_body + 1000:
                        r_dict[k] = new_body + (r_dict[k] - old_body)
            db2.execute(f"INSERT INTO {bt} ({', '.join(cols_bt)}) VALUES ({', '.join('?' * len(cols_bt))})", [r_dict[c] for c in cols_bt])
        print(f"      Cloned {len(donor_rows)} rows in {bt} for CarBodyID={new_body}")

    # 6) Clone Ordinal-keyed Upgrade Tables from donor
    upgrade_tables = [
        "List_AntiSwayPhysics", "List_SpringDamperPhysics", "List_UpgradeAntiSwayFront",
        "List_UpgradeAntiSwayRear", "List_UpgradeBrakes",
        "List_UpgradeDrivetrain", "List_UpgradeEngine", "List_UpgradeRearWing",
        "List_UpgradeRimSizeFront", "List_UpgradeRimSizeRear", "List_UpgradeSpringDamper",
        "List_UpgradeTireCompound"
    ]

    old_s = str(donor_car_id)
    new_s = str(new_car_id)

    for ut in upgrade_tables:
        db2.execute(f"DELETE FROM {ut} WHERE Ordinal = ?", (new_car_id,))
        donor_rows = db2.execute(f"SELECT * FROM {ut} WHERE Ordinal = ?", (donor_car_id,)).fetchall()
        cols_ut = [c[1] for c in db2.execute(f"PRAGMA table_info('{ut}')")]
        for dr in donor_rows:
            r_dict = dict(dr)
            r_dict["Ordinal"] = new_car_id
            for k, v in list(r_dict.items()):
                if k.lower().endswith("id") and isinstance(v, int) and str(v).startswith(old_s):
                    r_dict[k] = int(str(v).replace(old_s, new_s, 1))
            db2.execute(f"INSERT INTO {ut} ({', '.join(cols_ut)}) VALUES ({', '.join('?' * len(cols_ut))})", [r_dict[c] for c in cols_ut])
        print(f"      Cloned {len(donor_rows)} rows in {ut} for Ordinal={new_car_id}")

    db2.commit()
    db1.close()
    db2.close()
    print("      Database updates committed successfully.")


def inject_stringtables(fh1_str_dir: str, fh2_str_dir: str, k_disp: int = 22844, k_short: int = 24312):
    """Injects localized car names into all 18 FH2 string table zip files."""
    print(f"\n[3/4] Injecting string tables into {fh2_str_dir}")

    for lang in LANGS:
        zp1 = os.path.join(fh1_str_dir, lang + ".zip")
        if not os.path.exists(zp1):
            zp1 = os.path.join(fh1_str_dir, lang.upper() + ".zip")
        if not os.path.exists(zp1):
            zp1 = os.path.join(fh1_str_dir, lang.lower() + ".zip")

        disp_text = "Audi R8 GT"
        short_text = "R8 GT"

        if os.path.exists(zp1):
            try:
                d1 = fh1zip.read(zp1, "Data_Car.str")
                s1 = parse_lsb2_be(d1)
                disp_text = s1.get(k_disp, disp_text)
                short_text = s1.get(k_short, short_text)
            except Exception:
                pass

        zp2 = os.path.join(fh2_str_dir, lang + ".zip")
        if not os.path.exists(zp2):
            continue

        with zipfile.ZipFile(zp2) as z2:
            infos = z2.infolist()
            files = {i.filename: z2.read(i) for i in infos}

        target_name = next((n for n in files if n.lower() == "data_car.str"), None)
        if not target_name:
            continue

        lsb = strtables.Lsb2(files[target_name])
        lsb.strings[k_disp] = disp_text
        lsb.strings[k_short] = short_text
        files[target_name] = lsb.build()

        tmp = zp2 + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for i in infos:
                zout.writestr(i.filename, files[i.filename])
        os.replace(tmp, zp2)
        print(f"      Updated {lang}.zip: '{disp_text}' / '{short_text}'")


def update_manifests(j, car_zip_path: str, game_root: str):
    """Registers the new car zip in zipmanifest.xml and hash.manifest."""
    print(f"\n[4/4] Updating manifests for {car_zip_path}")
    fh3port.manifest_set(j, car_zip_path)
    fh3port.hm_register(j, car_zip_path)
    fh3port.save_journal(j)
    print("      Manifests updated successfully.")


def port_car(fh1_car_name: str, donor_car_name: str, new_car_id: int = 2755,
             fh1_root: str = FH1_DEFAULT_ROOT, game_root: str = GAME_DEFAULT_ROOT):
    """Executes the full end-to-end porting pipeline for an FH1 car."""
    j = fh3port.journal()

    fh1_zip_path = os.path.join(fh1_root, "Media", "cars", f"{fh1_car_name}.zip")
    donor_zip_path = os.path.join(game_root, "Mount", "media", "cars", f"{donor_car_name}.zip")
    out_zip_path = os.path.join(game_root, "Mount", "media", "cars", f"{fh1_car_name}.zip")

    fh1_db_path = os.path.join(fh1_root, "Media", "db", "gamedb.slt")
    fh2_db_path = os.path.join(game_root, "Mount", "media", "stripped", "gamedbRC.slt")

    fh1_str_dir = os.path.join(fh1_root, "Media", "StringTables")
    fh2_str_dir = os.path.join(game_root, "Mount", "media", "stripped", "stringtables")

    if not os.path.exists(fh1_zip_path):
        raise FileNotFoundError(f"FH1 car archive not found: {fh1_zip_path}")
    if not os.path.exists(donor_zip_path):
        raise FileNotFoundError(f"FH2 donor car archive not found: {donor_zip_path}")

    # Backups
    fh3port.touch(j, fh2_db_path)
    for lang in LANGS:
        zp = os.path.join(fh2_str_dir, lang + ".zip")
        if os.path.exists(zp):
            fh3port.touch(j, zp)

    # 1. Build car archive
    build_car_archive(fh1_zip_path, donor_zip_path, out_zip_path, fh1_car_name, donor_car_name, new_car_id)

    # 2. Database
    inject_database(fh1_db_path, fh2_db_path, fh1_car_name, donor_car_name, new_car_id)

    # 3. String tables
    inject_stringtables(fh1_str_dir, fh2_str_dir)

    # 4. Manifests
    update_manifests(j, out_zip_path, game_root)

    print("\n=================================================================")
    print(f" PORT SUCCESSFUL: {fh1_car_name} (CarId={new_car_id})")
    print(f" Archive: {out_zip_path}")
    print(f" Database: {fh2_db_path}")
    print("=================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Port FH1 car into FH2")
    sub = parser.add_subparsers(dest="command")

    p_port = sub.add_parser("port", help="Port an FH1 car")
    p_port.add_argument("fh1_car", help="MediaName of FH1 car (e.g. AUD_R8GT_11)")
    p_port.add_argument("donor_car", help="MediaName of FH2 donor car (e.g. AUD_R8Plus_13)")
    p_port.add_argument("--id", type=int, default=2755, help="New Car ID in FH2 (default: 2755)")
    p_port.add_argument("--fh1-root", default=FH1_DEFAULT_ROOT, help="FH1 extraction root")
    p_port.add_argument("--game-root", default=GAME_DEFAULT_ROOT, help="FH2 game root")

    args = parser.parse_args()
    if args.command == "port":
        port_car(args.fh1_car, args.donor_car, args.id, args.fh1_root, args.game_root)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
