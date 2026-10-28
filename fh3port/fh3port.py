"""
fh3port - port Forza Horizon 3 cars into Forza Horizon 2 (Mount folder).

    py fh3port.py setup                check the configured paths (fh3port.ini) and Python packages
    py fh3port.py plan                 list FH3 cars and what would happen to each (new / replace / skipped)
    py fh3port.py port <MediaName>...  port the given cars (or "all"); add --keep-plates to keep the licence plates
                                       (FH2 has no plate text, so they show zeros; hidden by default)
    py fh3port.py names [MediaName...] write the ported cars' names into every language's string table (all if none)
    py fh3port.py restore              put every backed-up file back and delete every file this tool created
    py fh3port.py status               show the journal (what was ported, backed up, created)

Every file is copied to FH3Port_Backup\\ (next to Mount) the first time it is touched; every created file and
ported car is logged in journal.json so "restore" can undo everything.
"""
import glob, json, os, re, shutil, sqlite3, struct, subprocess, sys, tempfile, zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtpr
import geom
import carbin
import tex
import mncl
import matmap
import lightparams
import slod
import zfight
import vlayfix
import aofix
import dbcheck
import plates
import physdef
import logos
import fh3lib
import paramexpand
import strtables
import prepatch
import dlc_synth

HERE = os.path.dirname(os.path.abspath(__file__))


def _config():
    """Paths from fh3port.ini next to this script ([paths] game / fh3 / converter). game defaults to the folder two
    levels up (<game>\\fh2sql\\fh3port), which is where the package is meant to be unpacked."""
    import configparser
    cp = configparser.ConfigParser()
    cp.read(os.path.join(HERE, "fh3port.ini"), encoding="utf-8")
    p = cp["paths"] if cp.has_section("paths") else {}

    # game: configured path if exists, else ../..
    game = p.get("game")
    default_game = os.path.dirname(os.path.dirname(HERE))
    if not game or not os.path.exists(game):
        game = default_game

    # fh3: the FH3 installation (holds media\); no default - set it in FH2 Mod Studio or fh3port.ini
    fh3 = p.get("fh3") or ""
    # fh3_extra: more FH3 media folders, ';'-separated, searched before <fh3>\media (update / DLC trees kept apart)
    extra = [x.strip() for x in (p.get("fh3_extra") or "").split(";") if x.strip()]
    fh3lib.set_roots(extra + [os.path.join(fh3, "media")] if fh3 else extra)
    EXTRA_MEDIA[:] = extra

    # converter: configured path if exists, else search known relative locations
    cli = p.get("converter")
    cli_candidates = [
        cli,
        os.path.join(HERE, "converter", "ForzaToolsCli.exe"),
        os.path.join(os.path.dirname(HERE), "Forza Horizon 2 Convertor", "ForzaToolsCli.exe"),
        os.path.join(os.path.dirname(os.path.dirname(HERE)), "Forza Horizon 2 Convertor", "ForzaToolsCli.exe"),
    ]
    cli = next((c for c in cli_candidates if c and os.path.exists(c)), cli_candidates[1])

    return game, os.path.join(fh3, "media") if fh3 else "", cli


EXTRA_MEDIA = []
GAME, FH3, CLI = _config()
MOUNT = os.path.join(GAME, "Mount")
FH2 = os.path.join(MOUNT, "media")
WORK = os.path.join(HERE, "work")
BACKUP = os.path.join(GAME, "FH3Port_Backup")
JOURNAL = os.path.join(BACKUP, "journal.json")

FH2_DB = os.path.join(FH2, "stripped", "gamedbRC.slt")
FH3_DB = fh3lib.find(os.path.join("stripped", "gamedbRC.slt")) or os.path.join(FH3, "stripped", "gamedbRC.slt")
FH3_STRINGTABLES = fh3lib.find(os.path.join("stripped", "stringtables")) or os.path.join(FH3, "stripped", "stringtables")
EXTRA_ZIPS = {}     # media name (lower) -> car zip picked by the user outside the media folders (port-cars <path.zip>)


def fh3_car_zips():
    """{media name lower: zip path} of every FH3 car zip in the media folders (first folder wins) plus picked zips."""
    out = {os.path.splitext(k)[0]: v for k, v in fh3lib.listdir("cars", ".zip").items()}
    out.update(EXTRA_ZIPS)
    return out


def use_zips(args):
    """Car arguments that are paths to a .zip (picked in FH2 Mod Studio, anywhere on disk) -> their media names; the
    zip is used instead of the media folders' copy. Inherited by child processes through FH3PORT_ZIPS."""
    out = []
    for a in args:
        if a.lower().endswith(".zip") and os.path.isfile(a):
            media = os.path.splitext(os.path.basename(a))[0]
            EXTRA_ZIPS[media.lower()] = os.path.abspath(a)
            a = media
        out.append(a)
    os.environ["FH3PORT_ZIPS"] = os.pathsep.join(EXTRA_ZIPS.values())
    if EXTRA_ZIPS:
        rows = {r[0].lower(): r[0] for r in open_ro(FH3_DB).execute("SELECT MediaName FROM Data_Car")} if os.path.exists(FH3_DB) else {}
        out = [rows.get(m.lower(), m) for m in out]
        for m in out:
            if m.lower() in EXTRA_ZIPS and m.lower() not in rows:
                print("   %s: the FH3 database has no car with this MediaName - name the zip like FH3 does "
                      "(e.g. por_918spyder_14.zip)" % m, flush=True)
    return out


for _z in filter(None, os.environ.get("FH3PORT_ZIPS", "").split(os.pathsep)):
    EXTRA_ZIPS[os.path.splitext(os.path.basename(_z))[0].lower()] = _z


def fh3_file(rel):
    """An FH3 media file (path relative to media\\) from the first media folder that has it."""
    return fh3lib.find(rel)
MANIFEST = os.path.join(FH2, "zipmanifest.xml")
FH2_LIB = os.path.join(FH2, "cars", "_library")
FH3_LIB = os.path.join((fh3lib.ROOTS or [FH3])[-1], "cars", "_library")   # LayeredZip spans every media folder
FH2_SHADERS = os.path.join(FH2, "_library", "Shaders.zip")
THUMB_ZIP = os.path.join(FH2, "stripped", "RCFH3.zip")          # new zip holding ported thumbnails
LIB_TEX_ZIP = os.path.join(FH2_LIB, "Textures.zip")              # missing FH3 library textures are appended here

# tables whose rows describe game content (events, career, profiles) rather than the car itself
EXCLUDE_TABLE = re.compile(r"^(NewProfile_|Anthem|Event|Career|Reward|Bucket|MiniCareer|IslandIE|Rental|RaceParticipants|IEAutoShowCars|"
                           r"AuctionHouse|BarnFind|Rewards_)", re.I)
CAR_COLUMNS = ("carid", "ordinal", "carordinal")

# FH3 tyre compound -> FH2 compound (FH3 has 21, FH2 10; ids mean different compounds)
TIRE_MAP = {1: 1, 2: 1, 3: 2, 4: 3, 5: 2, 6: 3, 7: 4, 8: 6, 9: 5, 10: 6, 11: 6, 12: 7, 13: 8, 14: 9, 15: 9, 16: 9, 17: 9, 18: 7, 19: 8, 20: 9, 21: 9}
FH2_TIRE_SLOTS = 5   # tyre shop levels 0..5 in FH2


# ───────────── journal / backups ─────────────

def journal():
    if os.path.exists(JOURNAL):
        with open(JOURNAL, encoding="utf-8") as f:
            return json.load(f)
    return {"backups": {}, "created": [], "cars": {}}


def save_journal(j):
    os.makedirs(BACKUP, exist_ok=True)
    tmp = JOURNAL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(j, f, indent=1)
    os.replace(tmp, JOURNAL)


def touch(j, path):
    """Back up an existing file once (the very first original wins); remember files that did not exist.
    New files under Mount are also registered in hash.manifest - the game only sees files listed there."""
    rel = os.path.relpath(path, GAME)
    if rel in j["backups"] or rel in j["created"]:
        return
    if os.path.exists(path):
        dst = os.path.join(BACKUP, "files", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(path, dst)
        j["backups"][rel] = dst
    else:
        j["created"].append(rel)
        if os.path.abspath(path).lower().startswith(MOUNT.lower() + os.sep):
            hm_register(j, path)
    save_journal(j)


# ───────────── hash.manifest (the game's index of package files) ─────────────
# 12-byte records: u64 hash of the lowercased path relative to Mount (backslashes), u32 value. The value differs per
# file (looks like a content/chunk id); new files copy the value of a sibling, preferring the same extension.
# Azimuth refuses to start when Mount\hash.manifest differs from the original, so additions go to an extended copy
# in <game folder>\FH3Port\hash.manifest, which fh2sql.dll hands to the game when it opens hash.manifest.

HASH_ORIGINAL = os.path.join(MOUNT, "hash.manifest")
HASH_MANIFEST = os.path.join(GAME, "FH3Port", "hash.manifest")


def hm_hash(rel):
    s = rel.replace("/", "\\").lower().encode("latin1")
    h = 5381
    for c in s:
        h = (h ^ ((c + (h >> 2) + (h << 5)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    k = h
    for c in s:
        k = (k ^ ((c + (k >> 2) + (k << 5)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return h | (k << 32)


def hm_read():
    with open(HASH_MANIFEST if os.path.exists(HASH_MANIFEST) else HASH_ORIGINAL, "rb") as f:
        d = f.read()
    return {struct.unpack_from("<Q", d, i)[0]: struct.unpack_from("<I", d, i + 8)[0] for i in range(0, len(d) - len(d) % 12, 12)}


def hm_register(j, path):
    rel = os.path.relpath(os.path.abspath(path), MOUNT)
    recs = hm_read()
    key = hm_hash(rel)
    if key in recs:
        return
    folder = os.path.dirname(os.path.abspath(path))
    ext = os.path.splitext(path)[1].lower()
    value = None
    if os.path.isdir(folder):
        sibs = sorted(os.listdir(folder), key=lambda n: (os.path.splitext(n)[1].lower() != ext, n.lower()))
        for n in sibs:
            v = recs.get(hm_hash(os.path.relpath(os.path.join(folder, n), MOUNT)))
            if v is not None:
                value = v
                break
    if value is None:
        value = recs.get(hm_hash(os.path.relpath(folder, MOUNT)), 1)
    if not os.path.exists(HASH_MANIFEST):
        touch(j, HASH_MANIFEST)            # logged as created, so "restore" deletes it
        os.makedirs(os.path.dirname(HASH_MANIFEST), exist_ok=True)
        shutil.copy2(HASH_ORIGINAL, HASH_MANIFEST)
    with open(HASH_MANIFEST, "ab") as f:
        f.write(struct.pack("<QI", key, value))
    j.setdefault("hash_manifest", {})[rel] = value


def restore():
    j = journal()
    for rel, src in j["backups"].items():
        shutil.copy2(src, os.path.join(GAME, rel))
        print("restored", rel)
    for rel in j["created"]:
        p = os.path.join(GAME, rel)
        if os.path.exists(p):
            os.remove(p)
            print("deleted", rel)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.replace(JOURNAL, JOURNAL.replace(".json", "_restored_%s.json" % stamp))
    print("done - backups kept in", BACKUP)


# ───────────── databases ─────────────

def open_ro(p):
    db = sqlite3.connect("file:%s?mode=ro&immutable=1" % p, uri=True)
    db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return db


def cols(db, t):
    return [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]


def tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def qi(s):
    return '"%s"' % s.replace('"', '""')


# ───────────── FH3 strings (en) ─────────────

class Fh3Strings:
    """FH3 .str: u32[6] header (count at [5]), count x (u32 low32-of-hash, u32 byte offset), UTF-16 pool."""
    def __init__(self):
        self.z = zipfile.ZipFile(os.path.join(FH3_STRINGTABLES, "en.zip"))
        self.cache = {}

    def table(self, name):
        name = name.lower() + ".str"
        if name not in self.cache:
            m = {}
            if name in self.z.namelist():
                d = self.z.read(name)
                n = struct.unpack_from("<I", d, 20)[0]
                pool = 24 + n * 8
                for i in range(n):
                    k, o = struct.unpack_from("<II", d, 24 + i * 8)
                    p = pool + o
                    e = p
                    while e + 1 < len(d) and (d[e] or d[e + 1]):
                        e += 2
                    m[k] = d[p:e].decode("utf-16le", "replace")
            self.cache[name] = m
        return self.cache[name]

    def text(self, table, value):
        if not isinstance(value, str) or not value.startswith("_&"):
            return value
        try:
            key = int(value[2:]) & 0xFFFFFFFF
        except ValueError:
            return value
        return self.table(table).get(key)


# ───────────── FH2-native zip layout ─────────────
# Every entry of FH2's own zips carries a central-directory extra field 0x1123 (4 bytes) = absolute offset of the
# entry's data, so the game can seek straight to it. Zips we write or extend get the same layout.

import zlib


def _raw_entries(path):
    """[(name, method, crc, csize, usize, dostime, dosdate, raw_bytes)] read straight from the file."""
    out = []
    with zipfile.ZipFile(path) as z, open(path, "rb") as f:
        for i in z.infolist():
            f.seek(i.header_offset)
            h = f.read(30)
            nlen, xlen = struct.unpack_from("<HH", h, 26)
            f.seek(i.header_offset + 30 + nlen + xlen)
            t, d = _dos(i.date_time)
            out.append((i.filename, i.compress_type, i.CRC, i.compress_size, i.file_size, t, d, f.read(i.compress_size)))
    return out


def _dos(dt):
    y, mo, d, h, mi, s = dt
    return (h << 11) | (mi << 5) | (s // 2), ((max(y, 1980) - 1980) << 9) | (mo << 5) | d


def _entry_from_bytes(name, data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    comp = c.compress(data) + c.flush()
    method, raw = (8, comp) if len(comp) < len(data) else (0, data)
    t, d = _dos(datetime.now().timetuple()[:6])
    return (name, method, zlib.crc32(data) & 0xFFFFFFFF, len(raw), len(data), t, d, raw)


def write_native_zip(path, entries):
    """Writes entries (from _raw_entries / _entry_from_bytes) as an FH2-layout zip."""
    tmp = path + ".tmp"
    central = []
    with open(tmp, "wb") as f:
        for name, method, crc, csize, usize, t, d, raw in entries:
            n = name.encode("utf-8")
            off = f.tell()
            f.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, method, t, d, crc, csize, usize, len(n), 0) + n)
            f.write(raw)
            extra = struct.pack("<HHI", 0x1123, 4, off + 30 + len(n))
            central.append(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, method, t, d, crc, csize, usize,
                                       len(n), len(extra), 0, 0, 0, 0, off) + n + extra)
        cd = f.tell()
        for c in central:
            f.write(c)
        size = f.tell() - cd
        f.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central), size, cd, 0))
    os.replace(tmp, path)


def normalize_zip(src, dst):
    write_native_zip(dst, _raw_entries(src))


def append_native(path, files):
    """Adds {name: bytes} to an existing zip without rewriting its data: new entries go where the central directory
    was, then the old central records (verbatim) plus the new ones (with the 0x1123 field) are written after them."""
    with zipfile.ZipFile(path) as z:
        have = {n.lower() for n in z.namelist()}
        count = len(z.infolist())
    files = {n: b for n, b in files.items() if n.lower() not in have}
    if not files:
        return
    with open(path, "r+b") as f:
        f.seek(-22, 2)
        eocd = f.read(22)
        if eocd[:4] != b"PK\x05\x06":
            raise RuntimeError("unexpected zip end (comment present?) in " + path)
        cd_size, cd_off = struct.unpack_from("<II", eocd, 12)
        f.seek(cd_off)
        old_cd = f.read(cd_size)
        f.seek(cd_off)
        new_central = []
        for name, data in files.items():
            name_, method, crc, csize, usize, t, d, raw = _entry_from_bytes(name, data)
            n = name_.encode("utf-8")
            off = f.tell()
            f.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, method, t, d, crc, csize, usize, len(n), 0) + n)
            f.write(raw)
            extra = struct.pack("<HHI", 0x1123, 4, off + 30 + len(n))
            new_central.append(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, method, t, d, crc, csize, usize,
                                           len(n), len(extra), 0, 0, 0, 0, off) + n + extra)
        cd = f.tell()
        f.write(old_cd)
        for c in new_central:
            f.write(c)
        size = f.tell() - cd
        total = count + len(new_central)
        f.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, total, total, size, cd, 0))
        f.truncate()


# ───────────── converter / zips / manifest ─────────────

ID_REMAP = {
    "mit_galantvr4_traffic_92": 3001,
    "maz_mazdaspeed3_traffic_10": 3002,
    "fia_500abarthss_traffic_10": 3003,
    "for_pursuitute_traffic_15": 3004,
}

TRAFFIC_PROPERTIES = {
    # media_name: (engine_id, drivetrain_id, stock_wheel_id)
    "mit_galantvr4_traffic_92": (841, 789, 11002),
    "maz_mazdaspeed3_traffic_10": (680, 623, 10759),
    "fia_500abarthss_traffic_10": (563, 511, 524),
    "for_pursuitute_traffic_15": (3004, 3004, 12803),
}


def run_cli(args):
    r = subprocess.run([CLI] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def convert_zip(src_zip, car_name, out_zip, keep_plates=False, new_car_id=None):
    if new_car_id is None:
        new_car_id = ID_REMAP.get(car_name.lower())
    prep_zip = out_zip + ".prep.zip"
    held = {}
    try:
        held = prepatch.prepare_zip(src_zip, car_name, prep_zip, FH3_LIB, os.path.dirname(os.path.dirname(FH3_LIB)))
        cli_in = prep_zip
    except Exception as e:
        print("   prepatch warning (using raw zip):", e)
        cli_in = src_zip
    rc, out = run_cli(["fix-materials", "--car", cli_in, "--car-name", car_name.lower(), "--fh3-lib", converter_fh3_lib(), "--fh2-lib", FH2_LIB,
                       "--fh2-shaders", FH2_SHADERS, "--out", out_zip, "--report-dir", os.path.join(WORK, "reports", car_name)])
    if os.path.exists(prep_zip):
        try:
            os.remove(prep_zip)
        except OSError:
            pass
    missing = re.findall(r"MISSING-IN-FH2 (\S+)", out)
    if rc == 0 and held:
        # paints prepatch kept from the converter (FH3-only paint shader): FH3 -> FH2 here; mncl remaps the shader
        with zipfile.ZipFile(out_zip, "a", zipfile.ZIP_DEFLATED) as z:
            have = {n.lower() for n in z.namelist()}
            for name, data in held.items():
                if name.lower() not in have:
                    data = mncl.convert_material(data)
                    lost = prepatch.MISSING_TEXTURES.get(name)
                    if lost:
                        mapping = {}
                        for p in lost:
                            near = mncl.closest_texture(p, library_texture_names())
                            if near:
                                mapping[p.lower()] = near
                                out += "\nprepatch: %s: texture %s is shipped nowhere, using %s" % (
                                    os.path.basename(name), p.rsplit("\\", 1)[-1], near.rsplit("\\", 1)[-1])
                        data = mncl.retarget_textures(data, mapping)
                    z.writestr(name, data)
        out += "\nprepatch: %d paints added after the converter (%s)" % (len(held), ", ".join(os.path.basename(n) for n in held))
    if rc == 0:
        tmp = out_zip + ".mtpr.zip"
        # remapped materials (FH3 shader absent in FH2) render black with the converter's guessed shader:
        # replace them with real FH2 library materials
        report = os.path.join(WORK, "reports", car_name, "fix_report.md")
        remaps = matmap.remaps_from_report(open(report, encoding="utf-8").read()) if os.path.exists(report) else []
        if remaps:
            log = matmap.apply(out_zip, tmp, remaps, matmap.Library(os.path.join(FH2_LIB, "Materials.zip")))
            os.replace(tmp, out_zip)
            out += "\nmatmap:\n   " + "\n   ".join(log)
        # the converter leaves FH3 (v3, GUID) parameters in material instances nested in modelbins; FH2 crashes on them
        n = mtpr.fix_zip(out_zip, tmp)
        os.replace(tmp, out_zip)
        out += "\nmtpr: rewrote FH3 material parameters in %d files" % n
        # FH3 light parameter names (Light Parameter, LightColor, CH1LightMap...) -> FH2's, so the lights switch on
        stats = lightparams.fix_zip(out_zip, tmp, car_name, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS)
        os.replace(tmp, out_zip)
        out += "\nlightparams: " + (", ".join("%s x%d" % kv for kv in sorted(stats.items())) or "nothing renamed")
        # ... and FH3 colour / gloss / reflectance parameters FH2 splits in two (white-and-red interiors otherwise)
        stats = paramexpand.fix_zip(out_zip, tmp, car_name, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS,
                                    os.path.join(FH3_LIB, "Materials.zip"))
        os.replace(tmp, out_zip)
        out += "\nparamexpand: %(instances)d instances, %(materials)d materials (%(restored)d colours restored)" % stats
        # ... and FH3 geometry (packed vertices, Mesh 1.8 / Modl 1.2 / Skel 1.0) that FH2 misreads
        n = geom.fix_zip(out_zip, tmp)
        os.replace(tmp, out_zip)
        out += "\ngeom: converted FH3 geometry in %d modelbins" % n
        # ... and the carbin (FH3 model entries are v16; FH2 reads up to v15 and misreads everything after entry 1)
        n = carbin.fix_zip(out_zip, tmp, car_name, os.path.join(FH2_LIB, "Materials.zip"), new_car_id=new_car_id)
        os.replace(tmp, out_zip)
        out += "\ncarbin: downgraded %d carbins" % n
        # ... and models with empty AO maps (FH3 NSX lamps): FH2 leaves the AO slot null -> black
        log = aofix.fix_zip(out_zip, tmp, car_name)
        os.replace(tmp, out_zip)
        out += "\naofix: " + ("; ".join(log) or "none")
        # ... and visible parts FH3 keeps only at LOD S (honeycomb grilles) that FH2 never draws
        log = slod.fix_zip(out_zip, tmp, car_name)
        os.replace(tmp, out_zip)
        out += "\nslod: " + ("; ".join(log) or "nothing to promote")
        # ... and opaque parts lying on glass overlays (z-fighting in FH2)
        log = zfight.fix_zip(out_zip, tmp)
        os.replace(tmp, out_zip)
        out += "\nzfight: " + ("; ".join(log) or "none")
        # ... and vertex layouts that match none of their FH2 shader's compiled variants exactly (black/shimmering parts)
        log = fix_vertex_layouts(out_zip, tmp, car_name)
        os.replace(tmp, out_zip)
        out += "\nvlayfix: %d layout changes" % len(log) + "".join("\n   " + x for x in log)
        # ... and FH3 UI textures (header byte +31 = 2) that FH2 takes for one-sided cubemaps -> white
        n = tex.fix_zip(out_zip, tmp)
        os.replace(tmp, out_zip)
        out += "\ntex: fixed %d textures" % n
        # ... and the paint list (MNCL blob 1.1 with u32 masks; FH2 reads 1.0 with u16)
        del mncl.WARNINGS[:]
        n = mncl.fix_zip(out_zip, tmp, car_name, os.path.join(FH2_LIB, "Materials.zip"), os.path.join(FH3_LIB, "Materials.zip"))
        os.replace(tmp, out_zip)
        out += "\nmncl: downgraded %d paint lists" % n + "".join("\n   " + w for w in mncl.WARNINGS)
        # ... and the collision shapes (FH2 loads them into a 4 KB arena; FH3's 4-cloud cars crash it)
        log = physdef.fix_zip(out_zip, tmp)
        os.replace(tmp, out_zip)
        out += "\nphysdef: " + ("; ".join(log) or "fits")
        # ... and the licence plates (FH2 has no plate text: a row of zeros) unless asked to keep them
        if not keep_plates:
            log = plates.fix_zip(out_zip, tmp)
            os.replace(tmp, out_zip)
            out += "\nplates: " + ("; ".join(log) or "none")
    return rc, out, missing


def fix_vertex_layouts(src, dst, car_name):
    """vlayfix with shader variants resolved per material path (car zip -> FH2 library -> MATL -> Shaders.zip)."""
    with zipfile.ZipFile(src) as z:
        names = {n.lower(): n for n in z.namelist()}
        res = lightparams.Resolver(names, z.read, car_name, os.path.join(FH2_LIB, "Materials.zip"), FH2_SHADERS)
        cache = {}

        def variants(material_path):
            key = material_path.lower()
            if key not in cache:
                md = res.material_bytes(material_path)
                sp = res.shader_of_material(md) if md else None
                sd = res.shader_bytes(sp) if sp else None
                cache[key] = vlayfix.vdcl_masks(sd) if sd else None
            return cache[key]

        return vlayfix.fix_zip(src, dst, variants)


def manifest_set(j, zip_path):
    """Add or replace the <Zip .../> line for zip_path in zipmanifest.xml (paths compared case-insensitively)."""
    rc, out = run_cli(["manifest-line", zip_path])
    line = next((l.strip() for l in out.splitlines() if l.strip().startswith("<Zip ")), None)
    if rc != 0 or not line:
        raise RuntimeError("manifest-line failed for %s: %s" % (zip_path, out[-400:]))
    game_path = "game:\\" + os.path.relpath(zip_path, MOUNT).lower()
    line = re.sub(r'path="[^"]*"', lambda _: 'path="%s"' % game_path, line)
    touch(j, MANIFEST)
    with open(MANIFEST, encoding="utf-8") as f:
        text = f.read()
    pat = re.compile(r'^[ \t]*<Zip [^>]*path="%s"[^>]*/>[ \t]*\r?\n' % re.escape(game_path), re.I | re.M)
    nl = "\r\n" if "\r\n" in text else "\n"
    if pat.search(text):
        text = pat.sub(lambda m: "  " + line + nl, text, count=1)
    else:
        text = text.replace("</ZipFiles>", "  " + line + nl + "</ZipFiles>")
    with open(MANIFEST, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    rc, out = run_cli(["manifest-check", zip_path, MANIFEST])
    # the checker guesses the path as media\cars\<zip> - for other folders only the three numbers count
    numbers_ok = all(re.search(r"%s\s+manifest=\d+\s+zip=\d+\s+OK" % k, out) for k in ("dirstart", "dirsize", "direntries"))
    if "MANIFEST OK" not in out and not numbers_ok:
        raise RuntimeError("manifest-check failed for %s: %s" % (zip_path, out[-400:]))


def downgrade_files(files):
    """files: {name: bytes} FH3 swatchbins -> FH2 1.0 containers, via the converter (it downgrades car-owned swatchbins)."""
    os.makedirs(WORK, exist_ok=True)
    fake = os.path.join(WORK, "_downgrade_in.zip")
    out = os.path.join(WORK, "_downgrade_out.zip")
    with zipfile.ZipFile(fake, "w", zipfile.ZIP_STORED) as z:
        for i, (name, data) in enumerate(files.items()):
            z.writestr("textures/%04d.swatchbin" % i, data)
    rc, log, _ = convert_zip(fake, "downgrade", out)
    if rc != 0:
        raise RuntimeError("downgrade failed: " + log[-400:])
    with zipfile.ZipFile(out) as z:
        return {name: z.read("textures/%04d.swatchbin" % i) for i, name in enumerate(files)}


def append_to_zip(j, zip_path, files):
    """Adds entries to a zip in FH2's layout (no full rewrite) and re-registers it in the manifest."""
    touch(j, zip_path)
    if os.path.exists(zip_path):
        append_native(zip_path, files)
    else:
        write_native_zip(zip_path, [_entry_from_bytes(n, b) for n, b in files.items()])
    manifest_set(j, zip_path)


def install_zip(j, src, dest):
    """Copies a converted zip into the game in FH2's layout and registers it."""
    touch(j, dest)
    normalize_zip(src, dest)
    manifest_set(j, dest)


_fh3_lib_index = None


_rc_index = None


def fh3_thumbnails(car):
    """{zip name: bytes} of a car's FH3 thumbnail swatchbins. FH3's Thumbnail path names an RC zip (RC21\\Thumbnail_2734
    for the Hoonicorn, whose id is 1184) or only UI\\Textures\\Thumbnails\\Thumbnail_<id>.png (DB11, Miata ...); the
    swatchbins live in some media folder's stripped\\RC*.zip, so every RC zip is searched, for the id in the path first
    and then the car's id."""
    global _rc_index
    if _rc_index is None:
        _rc_index = {}
        for f, zp in sorted(fh3lib.listdir("stripped", ".zip").items()):
            if re.fullmatch(r"rc\w*\.zip", f) and "hires" not in f:
                with zipfile.ZipFile(zp) as z:
                    for n in z.namelist():
                        m = re.fullmatch(r"(?i)(?:thumbnail_(\d+)(?:_big|_small)?|b_(\d+))\.swatchbin", n)
                        if m:
                            _rc_index.setdefault(int(m.group(1) or m.group(2)), {}).setdefault(n.lower(), (zp, n))
    ids = [int(x) for x in re.findall(r"(?i)thumbnail_(\d+)", car.get("Thumbnail") or "")] + [car["Id"]]
    for i in ids:
        if i in _rc_index:
            out = {}
            for zp, n in _rc_index[i].values():
                with zipfile.ZipFile(zp) as z:
                    out[n] = z.read(n)
            return out
    return {}


_lib_tex_names = None


def library_texture_names():
    """Lower-case names inside FH2's cars/_library/Textures.zip and FH3's layered one (missing ones get imported)."""
    global _lib_tex_names
    if _lib_tex_names is None:
        with zipfile.ZipFile(LIB_TEX_ZIP) as z:
            _lib_tex_names = {n.lower() for n in z.namelist()}
        with fh3lib.LayeredZip(os.path.join(FH3_LIB, "Textures.zip")) as lz:
            _lib_tex_names |= set(lz.index)
    return _lib_tex_names


def converter_fh3_lib():
    """--fh3-lib for the converter: FH3's cars/_library, or with several media folders / patch zips a folder whose
    Materials.zip merges every layer (the converter reads one Materials.zip)."""
    base = os.path.join(FH3_LIB, "Materials.zip")
    if len(fh3lib.layers(base)) <= 1:
        return FH3_LIB
    fh3lib.merged_zip(base, os.path.join(WORK, "fh3lib", "Materials.zip"))
    return os.path.join(WORK, "fh3lib")


def fh3_library_file(game_path):
    """game:\\media\\cars\\_library\\textures\\x\\y.swatchbin -> bytes from FH3's library zips (zip X.zip is folder X)."""
    global _fh3_lib_index
    if _fh3_lib_index is None:
        _fh3_lib_index = {}
        for media in fh3lib.ROOTS:                       # first media folder wins
          for root, _, fs in os.walk(media):
            for f in sorted(fs, key=fh3lib.priority):     # Textures_pri_45 > _pri_44 > Textures.zip
                if f.lower().endswith(".zip") and "_library" in root.lower():
                    zp = os.path.join(root, f)
                    # Textures_pri_44.zip overlays the same folder as Textures.zip; keys are relative to media\
                    folder = os.path.relpath(os.path.join(root, re.sub(r"(?i)_pri_\d+$", "", f[:-4])), media).lower()
                    try:
                        with zipfile.ZipFile(zp) as z:
                            for n in z.namelist():
                                _fh3_lib_index.setdefault(os.path.join(folder, n.replace("/", "\\")).lower(), (zp, n))
                    except zipfile.BadZipFile:
                        pass
    rel = game_path.lower().replace("game:\\media\\", "").replace("/", "\\")
    hit = _fh3_lib_index.get(rel)
    if not hit:
        return None
    with zipfile.ZipFile(hit[0]) as z:
        return z.read(hit[1])


LIB_TEX_PREFIX = "game:\\media\\cars\\_library\\textures\\"
_fh2_lib_textures = None


def texture_refs(zip_path):
    """All Texture2D paths (lowercase) set by the materials and material instances in a converted car zip."""
    refs = set()

    def s7(b, p):
        n = s = 0
        while True:
            c = b[p]; p += 1
            n |= (c & 0x7F) << s; s += 7
            if not c & 0x80:
                return b[p:p + n].decode("latin1")

    def walk(d):
        for tag, ver, ep, doff, size in mtpr.blobs(d):
            b = d[doff:doff + size]
            if tag[::-1] == b"MTPR":
                params, _ = mtpr.parse_params(b, None)
                for start, end, maj, mn, h, typ in params:
                    if typ == 6:
                        refs.add(s7(b, start + 7 + (16 if maj >= 3 else 0)).lower())
            elif tag[::-1] == b"MatI":
                walk(b)

    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.lower().endswith((".modelbin", ".materialbin")):
                walk(z.read(n))
    return refs


def missing_library_textures(zip_path):
    """Shared-library textures a car references that FH2's cars\\_library\\Textures*.zip doesn't have. The converter
    only reports the ones referenced from the carbin; material/instance references (grille patterns, light masks,
    screws, grain normals...) were silently left dangling and render black/flat."""
    global _fh2_lib_textures
    if _fh2_lib_textures is None:
        _fh2_lib_textures = set()
        for p in glob.glob(os.path.join(FH2_LIB, "Textures*.zip")):
            with zipfile.ZipFile(p) as z:
                _fh2_lib_textures.update(n.lower() for n in z.namelist())
    return sorted(r for r in texture_refs(zip_path)
                  if r.startswith(LIB_TEX_PREFIX) and r[len(LIB_TEX_PREFIX):].replace("\\", "/") not in _fh2_lib_textures)


# ───────────── database port ─────────────

class Porter:
    def __init__(self, j, fh2_path):
        self.j = j
        self.ported_now = set()
        self.fh3 = open_ro(FH3_DB)
        self.fh2 = sqlite3.connect(fh2_path)
        self.fh2.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
        self.t2, self.t3 = tables(self.fh2), tables(self.fh3)
        self.common = self.t2 & self.t3
        self.strings = Fh3Strings()
        self.cols2 = {t: cols(self.fh2, t) for t in self.common}
        self.cols3 = {t: cols(self.fh3, t) for t in self.common}
        self.car_tables = {t: c for t in self.common if not EXCLUDE_TABLE.match(t) and t != "Data_Car"
                           for c in self.cols3[t] if c.lower() in CAR_COLUMNS}
        self.key_tables = {k: [t for t in self.common if not EXCLUDE_TABLE.match(t) and any(c.lower() == k.lower() for c in self.cols3[t])]
                           for k in ("EngineID", "DrivetrainID", "CarBodyID", "MotorID")}
        # tables whose first column is an "...ID" key: targets for reference columns of ported rows
        pk = {}
        for t in self.common:
            k = self.cols3[t][0]
            if k.lower().endswith("id") and k.lower() != "id":
                pk.setdefault(k.lower(), []).append(t)
        self.pk = {k: v[0] for k, v in pk.items() if len(v) == 1}
        self.unresolved = set()
        self.tire_models = set()
        self.log = []
        self.validator = dbcheck.Validator(self)

    # reference columns whose target key is named differently
    ALIASES = {"torquecurvefullthrottleid": ("List_TorqueCurve", "TorqueCurveID"),
               "manufacturerid": ("List_PartManufacturer", "Id"), "partmanufacturerid": ("List_PartManufacturer", "Id")}
    # referenced rows owned by the car's engine: overwrite FH2's (a replaced car brings its own curves)
    OWNED_REFS = {"List_TorqueCurve"}

    def ref_target(self, col, table):
        c = col.lower()
        if c in self.ALIASES:
            return self.ALIASES[c]
        if c in ("tirecompoundid", "id") or not c.endswith("id"):
            return None
        best = max((k for k in self.pk if c.endswith(k) and self.pk[k] != table), key=len, default=None)
        return (self.pk[best], self.cols3[self.pk[best]][0]) if best else None

    def fill_refs(self, table, cc, rows):
        """Copies rows that ported rows point at (aero physics, curves, ...) when FH2 doesn't have them. Never overwrites."""
        n = 0
        for ci, c in enumerate(cc):
            if ci == 0 or not c.lower().endswith("id"):
                continue
            target = self.ref_target(c, table)
            if not target:
                self.unresolved.add("%s.%s" % (table, c))
                continue
            tt, kc = target
            if tt not in self.common:
                continue
            owned = tt in self.OWNED_REFS
            for v in {r[ci] for r in rows if r[ci] not in (None, 0, -1, "")}:
                if not owned and self.fh2.execute("SELECT 1 FROM %s WHERE %s = ?" % (qi(tt), qi(kc)), (v,)).fetchone():
                    continue
                c3r, rr = self.rows3(tt, "%s = ?" % qi(kc), (v,))
                if rr:
                    n += self.insert(tt, c3r, [self.literal_strings(tt, c3r, r) for r in rr], replace=owned)
        return n

    def rows3(self, t, where, args=()):
        c = self.cols3[t]
        return c, self.fh3.execute('SELECT * FROM %s WHERE %s' % (qi(t), where), args).fetchall()

    def insert(self, t, c3, rows, replace=True):
        c2 = self.cols2[t]
        self.validator.before(t, c3, rows, replace)
        use = [c for c in c3 if c in c2]
        idx = [c3.index(c) for c in use]
        sql = "INSERT OR %s INTO %s (%s) VALUES (%s)" % ("REPLACE" if replace else "IGNORE", qi(t), ",".join(qi(c) for c in use), ",".join("?" * len(use)))
        self.fh2.executemany(sql, [[r[i] for i in idx] for r in rows])
        return len(rows) + (self.fill_refs(t, c3, rows) if replace else 0)

    def col_of(self, t, name):
        return next((c for c in self.cols3[t] if c.lower() == name.lower()), None)

    def ids_from(self, t, col, ordinal):
        c = self.col_of(t, col)
        return sorted({r[0] for r in self.fh3.execute('SELECT %s FROM %s WHERE Ordinal = ?' % (qi(c), qi(t)), (ordinal,)) if r[0] is not None})

    def port_car(self, car3, fh2_existing_id, remap_id=None):
        """car3: FH3 Data_Car row dict. Replaces FH2's version (fh2_existing_id) or adds a new car."""
        if dlc_synth.is_dlc_car(car3["MediaName"]) and not self.fh3.execute(
                "SELECT 1 FROM Data_Car WHERE MediaName = ? COLLATE NOCASE", (car3["MediaName"],)).fetchone():
            dlc_id = dlc_synth.synthesize_car_db(self, car3["MediaName"])
            self.ported_now.add(dlc_id)
            self.log.append("%s: synthesized DLC car id %d" % (car3["MediaName"], dlc_id))
            return 1

        if remap_id is None:
            remap_id = ID_REMAP.get(car3["MediaName"].lower())

        orig_id = car3["Id"]
        x = remap_id if remap_id is not None else orig_id
        orig_body = orig_id * 1000
        new_body = x * 1000
        n = 0

        props = TRAFFIC_PROPERTIES.get(car3["MediaName"].lower()) if remap_id else None
        target_engine = props[0] if props else None
        target_dt = props[1] if props else None
        target_wheel = props[2] if props else car3.get("StockWheelID")

        # 1) clear FH2 rows of the car being replaced (and of the FH3/remapped id, in case)
        for oid in {x, orig_id if not remap_id else None, fh2_existing_id} - {None}:
            self.fh2.execute("DELETE FROM Data_Car WHERE Id = ?", (oid,))
            for t, c in self.car_tables.items():
                if c in self.cols2[t]:
                    self.fh2.execute("DELETE FROM %s WHERE %s = ?" % (qi(t), qi(c)), (oid,))
        if remap_id:
            self.fh2.execute("DELETE FROM Data_CarBody WHERE Id = ?", (new_body,))
            for t in self.key_tables.get("CarBodyID", []):
                c = self.col_of(t, "CarBodyID")
                if c in self.cols2[t]:
                    self.fh2.execute("DELETE FROM %s WHERE %s = ?" % (qi(t), qi(c)), (new_body,))

        # 2) Data_Car
        c3 = self.cols3["Data_Car"]
        row = list(self.fh3.execute("SELECT * FROM Data_Car WHERE Id = ?", (orig_id,)).fetchone())
        if remap_id:
            row[c3.index("Id")] = x
            if target_wheel and "StockWheelID" in c3:
                row[c3.index("StockWheelID")] = target_wheel
        n += self.insert("Data_Car", c3, [row])

        # 3) car-keyed tables
        for t, c in self.car_tables.items():
            cc, rows = self.rows3(t, "%s = ?" % qi(c), (orig_id,))
            if remap_id:
                ci = cc.index(c)
                rows = [list(r) for r in rows]
                for r in rows:
                    r[ci] = x
                if t == "List_UpgradeCarBody":
                    if "CarBodyID" in cc:
                        cbi = cc.index("CarBodyID")
                        for r in rows:
                            if r[cbi] == orig_body: r[cbi] = new_body
                    if "Id" in cc:
                        idi = cc.index("Id")
                        for r in rows:
                            if r[idi] == orig_body: r[idi] = new_body
                elif t == "List_UpgradeEngine" and target_engine:
                    if "EngineID" in cc and "IsStock" in cc:
                        ei = cc.index("EngineID")
                        si = cc.index("IsStock")
                        for r in rows:
                            if r[si] == 1:
                                r[ei] = target_engine
                elif t == "List_UpgradeDrivetrain" and target_dt:
                    if "DrivetrainID" in cc and "IsStock" in cc:
                        di = cc.index("DrivetrainID")
                        si = cc.index("IsStock")
                        for r in rows:
                            if r[si] == 1:
                                r[di] = target_dt
            if t == "List_UpgradeTireCompound":
                rows = self.fix_tires(cc, rows)
            if rows:
                n += self.insert(t, cc, rows)

        # 4) engine / drivetrain / body / motor families: everything keyed by those ids
        fam_tables = {"EngineID": "List_UpgradeEngine", "DrivetrainID": "List_UpgradeDrivetrain",
                      "CarBodyID": "List_UpgradeCarBody", "MotorID": "List_UpgradeMotor"}
        fam = {k: self.ids_from(t, k, orig_id) if t in self.common else [] for k, t in fam_tables.items()}
        # a family id that a not-ported FH2 car also uses (e.g. the NSX's engine swap to the Huracan V10, engine
        # 2292) stays FH2's: replacing it would rewrite that other car's engine data and upgrade lists
        ported = {c.get("id") for c in self.j["cars"].values() if c.get("status") == "ported"} | self.ported_now | {x}
        all_engines = list(fam["EngineID"])
        for key, ids in fam.items():
            c2 = self.col_of(fam_tables[key], key) if fam_tables[key] in self.common else None
            shared = []
            for v in ids:
                users = {r[0] for r in self.fh2.execute("SELECT DISTINCT Ordinal FROM %s WHERE %s = ?" % (qi(fam_tables[key]), qi(c2)), (v,))}
                if users - ported:
                    shared.append(v)
            if shared:
                self.log.append("   %s %s shared with FH2 cars - kept FH2's rows" % (key, shared))
                fam[key] = [v for v in ids if v not in shared]
        self.ported_now.add(x)
        for key, ids in fam.items():
            if not ids or (remap_id and key in ("EngineID", "DrivetrainID")):
                continue
            for t in self.key_tables[key]:
                if t in self.car_tables:      # List_UpgradeEngine etc. already ported by car
                    continue
                c = self.col_of(t, key)
                marks = ",".join("?" * len(ids))
                if c in self.cols2[t]:
                    self.fh2.execute("DELETE FROM %s WHERE %s IN (%s)" % (qi(t), qi(c), marks), ids)
                cc, rows = self.rows3(t, "%s IN (%s)" % (qi(c), marks), ids)
                if rows:
                    if remap_id and key == "CarBodyID":
                        rows = [list(r) for r in rows]
                        cbi = cc.index(c)
                        idi = cc.index("Id") if "Id" in cc else None
                        for r in rows:
                            if r[cbi] == orig_body: r[cbi] = new_body
                            if idi is not None and orig_body <= r[idi] < orig_body + 1000:
                                r[idi] = new_body + (r[idi] - orig_body)
                    n += self.insert(t, cc, rows)
        for body in fam["CarBodyID"]:
            cc, rows = self.rows3("Data_CarBody", "Id = ?", (body,))
            if remap_id:
                rows = [list(r) for r in rows]
                idi = cc.index("Id")
                for r in rows:
                    if r[idi] == orig_body: r[idi] = new_body
            n += self.insert("Data_CarBody", cc, rows)

        if remap_id and target_engine == x:
            # Standalone engine clone for Pursuit Ute
            orig_eid = 2538
            cc, rows = self.rows3("Data_Engine", "EngineID = ?", (orig_eid,))
            rows = [list(r) for r in rows]
            for r in rows: r[cc.index("EngineID")] = x
            n += self.insert("Data_Engine", cc, rows)
            for t in self.key_tables.get("EngineID", []):
                if t in self.car_tables or t == "Data_Engine": continue
                c = self.col_of(t, "EngineID")
                cc, rows = self.rows3(t, "%s = ?" % qi(c), (orig_eid,))
                if rows:
                    rows = [list(r) for r in rows]
                    ei = cc.index(c)
                    idi = cc.index("Id") if "Id" in cc else None
                    for r in rows:
                        r[ei] = x
                        if idi is not None and orig_eid * 1000 <= r[idi] < (orig_eid + 1) * 1000:
                            r[idi] = x * 1000 + (r[idi] - orig_eid * 1000)
                    n += self.insert(t, cc, rows)
            orig_did = 2485
            cc, rows = self.rows3("Data_Drivetrain", "DrivetrainID = ?", (orig_did,))
            rows = [list(r) for r in rows]
            for r in rows: r[cc.index("DrivetrainID")] = x
            n += self.insert("Data_Drivetrain", cc, rows)

        # 5) stock wheel
        wheel = target_wheel if remap_id else car3.get("StockWheelID")
        if wheel is not None:
            cc, rows = self.rows3("List_Wheels", "ID = ?", (wheel,))
            if rows:
                n += self.insert("List_Wheels", cc, rows, replace=False)

        # 6) lookup rows FH2 doesn't have (makes, cylinders, suspension types, ...): insert, never overwrite
        n += self.fill_lookups(car3)

        # 7) names, price, thumbnail
        car_dict = dict(car3)
        car_dict["Id"] = x
        self.fix_car_row(car_dict)

        # 8) engine sound: FH2 loads PG_<Data_Engine.MediaName>.bank for every engine of the car
        #    (Audio_GetCarEngineBankIds 0x140292840); FH3 banks can't load, so borrow an FH2 engine's name
        #    Shared FH2 engines are included: their rows stay FH2's, but one pointing at a bank FH2 doesn't ship
        #    (engine 410 FOR_Transit_11, used by FH2's Transit and the Twerkstallion) gets a real one
        active_engine = target_engine if remap_id else all_engines
        engine_list = [active_engine] if isinstance(active_engine, int) else active_engine
        self.fix_engine_audio(x, engine_list)

        # 9) manufacturer + Autoshow category the way FH2 stores them
        self.fix_make_and_bucket(car_dict)
        self.log.append("%s: %d rows" % (car3["MediaName"], n))
        return n

    # ported car (FH3 MediaName) -> FH2 engine MediaName whose sound it borrows; others are matched automatically
    AUDIO_DONOR = {"ACU_NSX_16": "NIS_GTR_12",          # 3.5 twin-turbo V6 hybrid -> GT-R's 3.8 twin-turbo V6
                   "LAM_Bellissima_17": "LAM_LP7004_12"}   # Centenario 6.5 V12 = Aventador LP700-4's engine

    @staticmethod
    def audio_dir():
        return os.path.join(FH2, "audio", "fmodanthem", "durango")

    def fix_engine_audio(self, ordinal, engine_ids):
        banks = {f[3:-5].lower() for f in os.listdir(self.audio_dir())
                 if f.startswith("PG_") and f.endswith(".bank")}
        media = self.fh2.execute("SELECT MediaName FROM Data_Car WHERE Id = ?", (ordinal,)).fetchone()[0]
        cols = "EngineID, MediaName, ConfigID, CylinderID, AspirationID_Stock, EngineGraphingMaxPower"
        for eid in engine_ids:
            row = self.fh2.execute("SELECT %s FROM Data_Engine WHERE EngineID = ?" % cols, (eid,)).fetchone()
            if not row or (row[1] or "").lower() in banks:
                continue
            donor = self.AUDIO_DONOR.get(media)
            if not donor or donor.lower() not in banks:
                # a bank of the same car's variant first (FOR_Transit_11 -> FOR_TransitSSV_11: same year suffix, one
                # name extends the other), then the closest engine by specs
                stem, _, year = (row[1] or "").lower().rpartition("_")
                near = sorted(b for b in banks if stem and b.rpartition("_")[2] == year
                              and (b.rpartition("_")[0].startswith(stem) or stem.startswith(b.rpartition("_")[0])))
                donor = next((f[3:-5] for f in os.listdir(self.audio_dir()) if near and f[3:-5].lower() == near[0]), None)                     or self.audio_donor(row, media, banks, cols)
            if donor:
                self.fh2.execute("UPDATE Data_Engine SET MediaName = ? WHERE EngineID = ?", (donor, eid))
                self.log.append("   engine %d (%s) has no FH2 sound bank -> uses %s's engine sound" % (eid, row[1], donor))

    # FH3 car category (Data_Car_Buckets.CarBucket) -> FH2's. The other ids mean the same in both games (checked with
    # the 242 cars in both); FH2's 16 is Japanese roadsters and 29 classic muscle, and FH2 has no "Buggies".
    BUCKET_MAP = {16: 21,   # Vans and Utility -> FH2 21 (Transit SSV, F100, Bel Air ...)
                  29: 21,   # Rods and Customs -> FH2 21 (where FH2 keeps Bel Air, Impala, F100, Mercury Coupe)
                  41: 38}   # Buggies -> FH2 38 Extreme Offroad (Rally Fighter, Nemesis, trophy trucks)

    def fix_make_and_bucket(self, car3):
        """Make: matched by ManufacturerCode (FH2's row if it has the make; else FH3's row under its id if free, else a
        new id - FH3's Datsun id 124 is FH2's ROB). Data_Car.MakeName = the make's DisplayName exactly like FH2's own
        cars (a string id for FH2 makes); the porter used to write plain text, which put the cars outside their make
        in the menus."""
        x = car3["Id"]
        m3 = self.fh3.execute("SELECT * FROM List_CarMake WHERE ID = ?", (car3["MakeID"],)).fetchone()
        if m3:
            c3 = self.cols3["List_CarMake"]
            code = m3[c3.index("ManufacturerCode")]
            row2 = self.fh2.execute("SELECT ID FROM List_CarMake WHERE UPPER(ManufacturerCode) = UPPER(?)", (code,)).fetchone()
            if row2:
                mid = row2[0]
            else:
                mid = car3["MakeID"]
                if self.fh2.execute("SELECT 1 FROM List_CarMake WHERE ID = ?", (mid,)).fetchone():
                    mid = self.fh2.execute("SELECT MAX(ID) + 1 FROM List_CarMake").fetchone()[0]
                row = list(self.literal_strings("List_CarMake", c3, list(m3)))
                row[c3.index("ID")] = mid
                self.insert("List_CarMake", c3, [row], replace=False)
                self.log.append("   make %s added to FH2 as id %d" % (code, mid))
            name = self.fh2.execute("SELECT DisplayName FROM List_CarMake WHERE ID = ?", (mid,)).fetchone()[0]
            self.fh2.execute("UPDATE Data_Car SET MakeID = ?, MakeName = ? WHERE Id = ?", (mid, name, x))
        for b3, b2 in self.BUCKET_MAP.items():
            self.fh2.execute("UPDATE Data_Car_Buckets SET CarBucket = ? WHERE CarId = ? AND CarBucket = ?", (b2, x, b3))
        used = {r[0] for r in self.fh2.execute("SELECT DISTINCT CarBucket FROM Data_Car_Buckets WHERE CarId <> ?", (x,))}
        for (b,) in self.fh2.execute("SELECT CarBucket FROM Data_Car_Buckets WHERE CarId = ?", (x,)).fetchall():
            if b in used:
                continue
            # the category most FH2 cars of the same make and class are in (then: same class)
            car = self.fh2.execute("SELECT ClassID, MakeID FROM Data_Car WHERE Id = ?", (x,)).fetchone()
            q = ("SELECT b.CarBucket, COUNT(*) n FROM Data_Car_Buckets b JOIN Data_Car c ON c.Id = b.CarId "
                 "WHERE c.Id <> ? AND c.ClassID = ? %s AND b.CarBucket IN (%s) GROUP BY b.CarBucket ORDER BY n DESC LIMIT 1")
            ok = ",".join(str(int(u)) for u in used)
            row = self.fh2.execute(q % ("AND c.MakeID = ?", ok), (x, car[0], car[1])).fetchone() or                 self.fh2.execute(q % ("", ok), (x, car[0])).fetchone()
            if row:
                self.fh2.execute("UPDATE Data_Car_Buckets SET CarBucket = ? WHERE CarId = ? AND CarBucket = ?", (row[0], x, b))
                self.log.append("   category %r is not one FH2 uses -> %d (most common for its make and class)" % (b, row[0]))

    def audio_donor(self, row, media, banks, cols):
        """Closest FH2 engine with a sound bank: same cylinders, layout, aspiration, power; same make preferred."""
        _, _, config, cyl, asp, power = row
        best = None
        for _, name, c2, cy2, a2, p2 in self.fh2.execute("SELECT %s FROM Data_Engine" % cols):
            if not name or name.lower() not in banks:
                continue
            score = (cy2 == cyl) * 8 + (c2 == config) * 4 + (a2 == asp) * 2 + (name[:4].lower() == media[:4].lower()) \
                - abs((p2 or 0) - (power or 0)) / 1000.0
            if best is None or score > best[0]:
                best = (score, name)
        return best[1] if best else None

    def fix_tires(self, cc, rows):
        lvl, cid, stock, model = cc.index("Level"), cc.index("TireCompoundID"), cc.index("IsStock"), cc.index("TireModelName")
        out = []
        for r in rows:
            r = list(r)
            if r[lvl] > FH2_TIRE_SLOTS and r[stock] != 1:
                continue                      # no FH2 shop slot for it
            r[cid] = TIRE_MAP.get(r[cid], 5)
            if r[model]:
                self.tire_models.add(r[model])
            out.append(r)
        return out

    def remap_tire_model(self, old, new):
        self.fh2.execute("UPDATE List_UpgradeTireCompound SET TireModelName = ? WHERE TireModelName = ?", (new, old))

    LOOKUPS = [("MakeID", "List_CarMake"), ("CylinderID", "List_Cylinders"), ("MaterialTypeID", "List_MaterialType"),
               ("CountryID", "List_Country"), ("RegionID", "List_Region"), ("FamilyModelID", "List_FamilyModel"),
               ("FamilyBodyID", "List_FamilyBody"), ("FamilySpecialID", "List_FamilySpecial")]

    def fill_lookups(self, car3):
        n = 0
        for col, t in self.LOOKUPS:
            if t not in self.common or car3.get(col) is None:
                continue
            k = self.cols3[t][0]
            if self.fh2.execute("SELECT 1 FROM %s WHERE %s = ?" % (qi(t), qi(k)), (car3[col],)).fetchone():
                continue
            cc, rows = self.rows3(t, "%s = ?" % qi(k), (car3[col],))
            rows = [self.literal_strings(t, cc, r) for r in rows]
            n += self.insert(t, cc, rows, replace=False)
        # suspension types used by the car's physics: the type row and its physics XML (whoever inserted the row)
        types = {r[0] for r in self.fh3.execute("SELECT DISTINCT SuspensionPhysicsTypeID FROM List_SpringDamperPhysics WHERE Ordinal = ?", (car3["Id"],))}
        for st in types:
            cc, rows = self.rows3("List_SuspensionPhysicsType", "SuspensionPhysicsTypeID = ?", (st,))
            if not self.fh2.execute("SELECT 1 FROM List_SuspensionPhysicsType WHERE SuspensionPhysicsTypeID = ?", (st,)).fetchone():
                n += self.insert("List_SuspensionPhysicsType", cc, rows, replace=False)
            for r in rows:
                for v in r:
                    if isinstance(v, str) and v.lower().endswith(".xml"):
                        self.copy_physics_xml(v)
        return n

    def copy_physics_xml(self, game_path):
        rel = re.sub(r"(?i)^game:\\media\\", "", game_path)
        src, dst = fh3_file(rel) or os.path.join(FH3, rel), os.path.join(FH2, rel)
        if not os.path.exists(src):
            self.log.append("   physics file missing in FH3: " + game_path)
        elif not os.path.exists(dst):
            touch(self.j, dst)
            shutil.copy2(src, dst)

    def literal_strings(self, t, cc, row):
        row = list(row)
        for i, v in enumerate(row):
            if isinstance(v, str) and v.startswith("_&"):
                txt = self.strings.text(t, v)
                if txt:
                    row[i] = txt
        return row

    def fix_car_row(self, car3):
        x = car3["Id"]
        sets = {}
        for c in ("DisplayName", "ModelShort", "MakeName"):
            src = "List_CarMake" if c == "MakeName" else "Data_Car"
            txt = self.strings.text(src, car3.get(c))
            if txt:
                sets[c] = txt
        if (car3.get("BaseCost") or 0) <= 1:
            # FH3 has no price for this one: median FH2 price of the same class
            prices = sorted(r[0] for r in self.fh2.execute("SELECT BaseCost FROM Data_Car WHERE ClassID = ? AND BaseCost > 1", (car3["ClassID"],)))
            sets["BaseCost"] = prices[len(prices) // 2] if prices else 50000
        sets["IsPurchased"] = 1
        sets["IsInstalled"] = 1
        self.fh2.execute("UPDATE Data_Car SET %s WHERE Id = ?" % ", ".join("%s = ?" % qi(k) for k in sets), list(sets.values()) + [x])

    def set_thumbnail(self, car_id):
        self.fh2.execute("UPDATE Data_Car SET Thumbnail = ? WHERE Id = ?", ("game:\\Media\\Stripped\\RCFH3\\Thumbnail_%d.png" % car_id, car_id))


# ───────────── tyre models ─────────────

TIRES2 = os.path.join(FH2_LIB, "scene", "tires")
TIRES3_REL = os.path.join("cars", "_library", "scene", "tires")
TIRE_ALIASES = {"offroadmt": "offroad", "ow_offroadmt": "OW_offroad", "snow": "offroad", "ow_snow": "OW_offroad", "dually_c": "c",
                "gy_nascar": "b", "yellowwall_thin": "whiteWall"}


def _tire_names(folder):
    return {f[5:-4].lower(): f[5:-4] for f in os.listdir(folder) if f.lower().startswith("tire_") and f.lower().endswith(".zip")}


def tire_fallback(name, have):
    base = re.sub(r"(?i)^wet_", "", name)
    base = re.sub(r"(?i)_horizon(edition)?$", "", base)
    for c in (name, base, TIRE_ALIASES.get(base.lower(), "")):
        if c and c.lower() in have:
            return have[c.lower()]
    return "OW_a" if base.lower().startswith("ow_") else "a"


def install_tires(j, porter):
    """Tyre models FH2 lacks: convert FH3's tire_<name>.zip. The converter points bundled materials at
    game:\\media\\cars\\<tag>\\..., so models go to the tyre folder and the bundle to media\\cars\\<tag>.zip."""
    have2 = _tire_names(TIRES2)
    tires3 = fh3lib.listdir(TIRES3_REL, ".zip")                       # every media folder (DLC: tire_b_redline)
    have3 = {f[5:-4]: os.path.basename(p)[5:-4] for f, p in tires3.items() if f.startswith("tire_")}
    missing_lib = set()
    for name in sorted(porter.tire_models, key=str.lower):
        if name.lower() in have2:
            continue
        src = have3.get(name.lower())
        if src:
            tag = "fh3tire_" + src.lower()
            out = os.path.join(WORK, "tires", tag + ".zip")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            rc, log, missing = convert_zip(tires3["tire_%s.zip" % src.lower()], tag, out)
            if rc == 0:
                ents = _raw_entries(out)
                assets = [e for e in ents if e[0].lower().startswith(("materials/", "textures/"))]
                model = [e for e in ents if e not in assets]
                dest = os.path.join(TIRES2, "tire_%s.zip" % src)
                touch(j, dest)
                write_native_zip(dest, model)
                manifest_set(j, dest)
                if assets:
                    dest2 = os.path.join(FH2, "cars", tag + ".zip")
                    touch(j, dest2)
                    write_native_zip(dest2, assets)
                    manifest_set(j, dest2)
                have2[name.lower()] = src
                missing_lib.update(missing)
                porter.log.append("tyre model %s: converted from FH3" % name)
                continue
        fb = tire_fallback(name, have2)
        porter.remap_tire_model(name, fb)
        porter.log.append("tyre model %s: not convertible, using FH2's %s" % (name, fb))
    return missing_lib


# ───────────── per-car pipeline ─────────────

def fh3_cars():
    db = open_ro(FH3_DB)
    c = cols(db, "Data_Car")
    cars = {r[c.index("MediaName")].lower(): dict(zip(c, r)) for r in db.execute("SELECT * FROM Data_Car")}
    synths = dlc_synth.all_synth_cars(FH2_DB)     # only for cars FH3's database has no row for
    for m, d in synths.items():
        if m not in cars:
            cars[m] = d
    return cars


def fh2_cars():
    db = open_ro(FH2_DB)
    return {r[1].lower(): r[0] for r in db.execute("SELECT Id, MediaName FROM Data_Car")}, {r[0]: r[1] for r in db.execute("SELECT Id, MediaName FROM Data_Car")}


def plan():
    zips = {k: os.path.basename(v) for k, v in fh3_car_zips().items()}
    c3 = fh3_cars()
    by_name, by_id = fh2_cars()
    out = []
    for name, f in sorted(zips.items()):
        car = c3.get(name)
        if not car:
            out.append((f, "skip", "no FH3 database row"))
        elif name in ID_REMAP:
            new_id = ID_REMAP[name]
            out.append((f, "new", "remapped id %d (was %d)" % (new_id, car["Id"])))
        elif name in by_name and by_name[name] != car["Id"] and car["Id"] in by_id:
            out.append((f, "skip", "FH3 id %d is FH2's %s" % (car["Id"], by_id[car["Id"]])))
        elif name in by_name:
            out.append((f, "replace", "FH2 id %d" % by_name[name]))
        elif car["Id"] in by_id:
            out.append((f, "skip", "FH3 id %d already used by FH2's %s" % (car["Id"], by_id[car["Id"]])))
        else:
            out.append((f, "new", "id %d" % car["Id"]))
    return out


CONVERT_WORKERS = max(1, min(8, (os.cpu_count() or 2) // 2))


def _convert_job(job):
    """One car's conversion in a worker process: (rc, log, missing, extra library textures, error traceback)."""
    src, media, out_zip, keep_plates = job
    new_car_id = ID_REMAP.get(media.lower())
    try:
        rc, log, missing = convert_zip(src, media, out_zip, keep_plates, new_car_id=new_car_id)
        return rc, log, missing, (missing_library_textures(out_zip) if rc == 0 else []), None
    except Exception:
        import traceback
        return 1, "", [], [], traceback.format_exc()


def failed_entry(j, media, status, reason):
    """Journal entry of a car whose (re-)port failed. A car ported before keeps its old files and database rows (the
    failed run changed neither), so its previous entry is kept under "previous"."""
    old = j["cars"].get(media, {})
    entry = {"status": status, "reason": reason[:300]}
    prev = old if old.get("status") == "ported" else old.get("previous")
    if prev:
        entry["previous"] = prev
        print("   the version installed before stays in the game")
    return entry


def port(names, keep_plates=False):
    j = journal()
    os.makedirs(WORK, exist_ok=True)
    c3 = fh3_cars()
    by_name, _ = fh2_cars()
    todo = [p for p in plan() if p[1] != "skip" and (names == ["all"] or os.path.splitext(p[0])[0].lower() in [n.lower() for n in names])]
    if not todo:
        print("nothing to port"); return
    # database: work on a copy, swap in at the end
    touch(j, FH2_DB)
    work_db = os.path.join(WORK, "gamedbRC.work.slt")
    shutil.copy2(FH2_DB, work_db)
    porter = Porter(j, work_db)
    lib_missing, thumbs = set(), {}
    # convert every car first, several at once (each conversion is independent; ~40 s -> ~10 s per car on its own,
    # and CONVERT_WORKERS in parallel); installing and the database stay sequential below
    jobs = {}
    for f, action, why in todo:
        car = c3[os.path.splitext(f)[0].lower()]
        out_zip = os.path.join(WORK, "cars", car["MediaName"] + ".zip")
        os.makedirs(os.path.dirname(out_zip), exist_ok=True)
        jobs[f] = (fh3_car_zips()[os.path.splitext(f)[0].lower()], car["MediaName"], out_zip, keep_plates)
    converter_fh3_lib()                     # merged FH3 library, built once before the workers start
    workers = min(CONVERT_WORKERS, len(jobs))
    print("converting %d cars with %d workers" % (len(jobs), workers), flush=True)
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(workers) as ex:
            results = dict(zip(jobs, ex.map(_convert_job, jobs.values())))
    else:
        results = {f: _convert_job(job) for f, job in jobs.items()}
    for f, action, why in todo:
        media = os.path.splitext(f)[0]
        car = c3[media.lower()]
        print("==", media, action, why)
        out_zip = jobs[f][2]
        rc, log, missing, extra, error = results[f]
        if error or rc != 0:
            reason = error.strip().splitlines()[-1] if error else (log.strip().splitlines()[-1] if log.strip() else "rc %s" % rc)
            print("   convert FAILED:", reason)
            j["cars"][car["MediaName"]] = failed_entry(j, car["MediaName"], "convert-failed", reason)
            save_journal(j)
            continue
        lib_missing.update(missing)
        lib_missing.update(extra)
        print("   library textures missing in FH2: %d from the converter report, %d more from materials" % (len(missing), len(set(extra) - set(m.lower() for m in missing))))
        # database rows first, in a savepoint: a car that fails here leaves no rows and no installed files
        remap_id = ID_REMAP.get(media.lower())
        target_id = remap_id or car["Id"]
        porter.fh2.execute("SAVEPOINT car")
        porter.validator.reset()
        try:
            porter.port_car(car, by_name.get(media.lower()), remap_id=remap_id)
            # every row checked before it went in and read back now (dbcheck.py); errors fail the car
            errors, warnings = porter.validator.after(target_id)
            dbcheck.write_report(WORK, car["MediaName"], errors, warnings)
            print("   database check: %d errors, %d warnings (work/dbcheck/%s.txt)" %(len(errors), len(warnings), car["MediaName"]))
            if errors:
                raise RuntimeError("database check: " + "; ".join(errors[:3]))
        except Exception as e:
            porter.fh2.execute("ROLLBACK TO car")
            porter.fh2.execute("RELEASE car")
            print("   database port FAILED:", repr(e))
            j["cars"][car["MediaName"]] = failed_entry(j, car["MediaName"], "db-failed", repr(e))
            save_journal(j)
            continue
        porter.fh2.execute("RELEASE car")
        # install the car zip (keep FH2's file name when replacing)
        cars_dir = os.path.join(FH2, "cars")
        existing = next((e for e in os.listdir(cars_dir) if e.lower() == f.lower()), None)
        dest = os.path.join(cars_dir, existing or (car["MediaName"] + ".zip"))
        install_zip(j, out_zip, dest)
        # thumbnail swatchbins (Thumbnail_<n>_Big/_Small, B_<n>), stored under the car's id in RCFH3.zip
        found = fh3_thumbnails(car)
        for n, data in found.items():
            thumbs[re.sub(r"\d+", str(target_id), n, count=1)] = data
        if found:
            porter.set_thumbnail(target_id)
        else:
            print("   no FH3 thumbnail found for %s (%s)" % (car["MediaName"], car.get("Thumbnail")))
        j["cars"][car["MediaName"]] = {"status": "ported", "action": action, "id": target_id, "zip": os.path.relpath(dest, GAME),
                                      "missing_library": missing, "at": datetime.now().isoformat(timespec="seconds")}
        save_journal(j)
    # shared files: tyre models, thumbnails and missing library textures (downgraded to FH2 containers)
    lib_missing.update(install_tires(j, porter))
    # manufacturer logos FH2 can't load (makes it never shipped a car of, makes added from FH3) -> RCFH3.zip
    files, rows = logos.missing_logos(porter.fh2, porter.fh3, FH2,
                                      {r[0] for r in porter.fh2.execute("SELECT DISTINCT MakeID FROM Data_Car")})
    thumbs.update(files)
    for mid, (small, large) in rows.items():
        porter.fh2.execute("UPDATE List_CarMake SET IconPath = ?, IconPathLarge = ? WHERE ID = ?", (small, large, mid))
    if rows:
        porter.log.append("manufacturer logos added for %d makes" % len(rows))
    if thumbs:
        append_to_zip(j, THUMB_ZIP, downgrade_files(thumbs))
    if lib_missing:
        found = {}
        for p in sorted({m.lower() for m in lib_missing}):
            data = fh3_library_file(p)
            rel = re.sub(r"(?i)^game:\\media\\cars\\_library\\textures\\", "", p).replace("\\", "/")
            if data is not None:
                found[rel] = data
            else:
                print("   library texture not found in FH3:", p)
        if found:
            append_to_zip(j, LIB_TEX_ZIP, downgrade_files(found))
    # names in every language's string table (menus outside the Autoshow show only string ids)
    done = [c for c in j["cars"] if j["cars"][c].get("status") == "ported" and c.lower() in {n.lower() for n in names}]
    if names == ["all"]:
        done = [c for c in j["cars"] if j["cars"][c].get("status") == "ported"]
    write_names(j, porter.fh2, done)
    porter.fh2.commit()
    ok = porter.fh2.execute("PRAGMA integrity_check").fetchone()[0]
    porter.fh2.close()
    if ok != "ok":
        raise RuntimeError("database integrity check failed: " + ok)
    shutil.copy2(work_db, FH2_DB)
    print("\n".join(porter.log))
    if porter.unresolved:
        print("id columns with no matching table (left as FH3 values):", ", ".join(sorted(porter.unresolved)))
    print("database written:", FH2_DB)


STRINGTABLES = os.path.join(FH2, "stripped", "stringtables")


def write_names(j, db, medias):
    """String ids for the cars' names (Data_Car DisplayName/ModelShort) and for makes FH2 doesn't have (List_CarMake
    DisplayName/Profile, Data_Car.MakeName), with FH3's text in every language's string table (strtables.py)."""
    if not medias:
        return
    fh3 = open_ro(FH3_DB)
    names = strtables.Names(j, db, STRINGTABLES, FH3_STRINGTABLES)
    c3cols = cols(fh3, "Data_Car")
    makes = {}
    for media in medias:
        row3 = fh3.execute("SELECT * FROM Data_Car WHERE MediaName = ? COLLATE NOCASE", (media,)).fetchone()
        row2 = db.execute("SELECT Id, DisplayName, ModelShort, MakeID FROM Data_Car WHERE MediaName = ? COLLATE NOCASE",
                          (media,)).fetchone()
        if not row3 or not row2:
            continue
        car3 = dict(zip(c3cols, row3))
        disp = names.id_for("Data_Car", car3["DisplayName"], row2[1])
        model = names.id_for("Data_Car", car3["ModelShort"], row2[2])
        db.execute("UPDATE Data_Car SET DisplayName = COALESCE(?, DisplayName), ModelShort = COALESCE(?, ModelShort) "
                   "WHERE Id = ?", (disp, model, row2[0]))
        makes[row2[3]] = car3["MakeID"]
    m3cols = cols(fh3, "List_CarMake")
    for mid2, mid3 in makes.items():
        row = db.execute("SELECT DisplayName FROM List_CarMake WHERE ID = ?", (mid2,)).fetchone()
        if not row or (isinstance(row[0], str) and row[0].startswith("_&")):
            continue                        # FH2's own make: already has its string id
        r3 = fh3.execute("SELECT * FROM List_CarMake WHERE ID = ?", (mid3,)).fetchone()
        if not r3:
            continue
        m3 = dict(zip(m3cols, r3))
        dn = names.id_for("List_CarMake", m3.get("DisplayName"), row[0])
        pr = names.id_for("List_CarMake", m3.get("Profile"), None)
        if dn:
            db.execute("UPDATE List_CarMake SET DisplayName = ?, Profile = COALESCE(?, Profile) WHERE ID = ?", (dn, pr, mid2))
            db.execute("UPDATE Data_Car SET MakeName = ? WHERE MakeID = ?", (dn, mid2))
    n = names.write(lambda tmp, dest: install_zip(j, tmp, dest))
    save_journal(j)
    print("names: %d cars, %d string tables written" % (len(medias), n))


# Texts FH2 Mod Studio's drift suspension (DriftDragPack: Upgrades row 274, springs level 5) shows in the upgrade shop.
# Upgrades.str keys (string ids 0x7091 << 16 | key); free in every language of the stock tables.
UPGRADE_STRINGS = {
    0xD000: {"EN": "Drift Spring and Dampers", "DE": "Drift-Federn und Dämpfer", "FR": "Ressorts et amortisseurs drift",
             "ES": "Muelles y amortiguadores de drift", "IT": "Molle e ammortizzatori da drift",
             "BR": "Molas e amortecedores de drift"},
    0xD001: {"EN": "Install drift coilovers with an aggressive alignment and extra steering angle for controlled slides. "
                   "Adjustable springs, dampers and alignment.",
             "DE": "Drift-Gewindefahrwerk mit aggressiver Achsgeometrie und größerem Lenkeinschlag für kontrollierte "
                   "Drifts. Einstellbare Federn, Dämpfer und Geometrie.",
             "FR": "Combinés filetés drift avec une géométrie agressive et un angle de braquage accru pour des glisses "
                   "contrôlées. Ressorts, amortisseurs et géométrie réglables.",
             "ES": "Suspensión roscada de drift con alineación agresiva y mayor ángulo de giro para derrapes controlados. "
                   "Muelles, amortiguadores y alineación ajustables.",
             "IT": "Assetto a ghiera da drift con geometria aggressiva e maggiore angolo di sterzata per derapate "
                   "controllate. Molle, ammortizzatori e geometria regolabili.",
             "BR": "Coilovers de drift com alinhamento agressivo e maior ângulo de esterço para derrapagens controladas. "
                   "Molas, amortecedores e alinhamento ajustáveis."},
    # drift tyres (Upgrades row 275, tyre level 6)
    0xD002: {"EN": "Drift Tire Compound", "DE": "Drift-Reifenmischung", "FR": "Gomme drift",
             "ES": "Compuesto de neumático de drift", "IT": "Mescola da drift", "BR": "Composto de pneu de drift"},
    0xD003: {"EN": "Install a hard drift compound that breaks traction predictably and holds long slides. "
                   "Less grip than street tires.",
             "DE": "Harte Drift-Reifenmischung, die vorhersehbar die Haftung verliert und lange Drifts hält. "
                   "Weniger Grip als Straßenreifen.",
             "FR": "Gomme drift dure qui décroche de façon prévisible et tient les longues glisses. "
                   "Moins d'adhérence que les pneus route.",
             "ES": "Compuesto duro de drift que pierde tracción de forma predecible y mantiene derrapes largos. "
                   "Menos agarre que los neumáticos de calle.",
             "IT": "Mescola dura da drift che perde aderenza in modo prevedibile e mantiene le derapate lunghe. "
                   "Meno grip delle gomme stradali.",
             "BR": "Composto duro de drift que perde tração de forma previsível e mantém derrapagens longas. "
                   "Menos aderência que pneus de rua."},
}


def upgrade_strings_command():
    """fh3port.py upgrade-strings: puts UPGRADE_STRINGS into every language's Upgrades.str (English where there is no
    translation). Idempotent; the zips are backed up like every other file the porter changes."""
    j = journal()
    n = 0
    for lang in strtables.LANGS:
        zp = os.path.join(STRINGTABLES, lang + ".zip")
        if not os.path.exists(zp):
            continue
        with zipfile.ZipFile(zp) as z:
            infos = z.infolist()
            files = {i.filename: z.read(i) for i in infos}
        name = next((x for x in files if x.lower() == "upgrades.str"), None)
        if not name:
            continue
        t = strtables.Lsb2(files[name])
        changed = False
        for key, texts in UPGRADE_STRINGS.items():
            text = texts.get({"br": "BR", "MX": "ES"}.get(lang, lang), texts["EN"])
            if t.strings.get(key) != text:
                t.strings[key] = text
                changed = True
        if not changed:
            continue
        files[name] = t.build()
        tmp = zp + ".upgrades.tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
            for i in infos:
                zo.writestr(i.filename, files[i.filename])
        install_zip(j, tmp, zp)
        os.remove(tmp)
        n += 1
    save_journal(j)
    print("upgrade strings: %d string tables written" % n)


def names_command(medias):
    """fh3port.py names [MediaName... | all]: (re)writes the names of installed ported cars."""
    j = journal()
    if not medias or medias == ["all"]:
        medias = [c for c, v in j["cars"].items() if v.get("status") == "ported"]
    touch(j, FH2_DB)
    work_db = os.path.join(WORK, "gamedbRC.names.slt")
    os.makedirs(WORK, exist_ok=True)
    shutil.copy2(FH2_DB, work_db)
    db = sqlite3.connect(work_db)
    db.create_collation("LOCALIZED_NOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    write_names(j, db, medias)
    db.commit()
    ok = db.execute("PRAGMA integrity_check").fetchone()[0]
    db.close()
    if ok != "ok":
        raise RuntimeError("database integrity check failed: " + ok)
    shutil.copy2(work_db, FH2_DB)
    print("database written:", FH2_DB)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "setup":
        ok = True
        for label, path in [("FH2 game folder (Mount inside)", MOUNT), ("FH2 database", FH2_DB),
                            ("FH2 Mount\\hash.manifest", HASH_ORIGINAL), ("FH3 media folder", FH3)] + [("FH3 extra media folder", x) for x in EXTRA_MEDIA] + [
                            ("FH3 database", FH3_DB), ("converter ForzaToolsCli.exe", CLI)]:
            found = os.path.exists(path)
            ok &= found
            print("%-32s %-7s %s" % (label, "ok" if found else "MISSING", path))
        try:
            import numpy  # noqa: F401
            print("%-32s ok" % "python numpy")
        except ImportError:
            ok = False
            print("%-32s MISSING  (py -m pip install numpy)" % "python numpy")
        print("setup ok" if ok else "fix the MISSING entries (fh3port.ini, see GUIDE.md)")
    elif cmd == "plan":
        p = plan()
        for f, a, why in p:
            print("%-8s %-40s %s" % (a, f, why))
        print({a: sum(1 for x in p if x[1] == a) for a in ("new", "replace", "skip")})
        db3, db2 = open_ro(FH3_DB), open_ro(FH2_DB)
        common = tables(db3) & tables(db2)
        per_car = sorted("%s.%s" % (t, c) for t in common if not EXCLUDE_TABLE.match(t) for c in cols(db3, t) if c.lower() in CAR_COLUMNS)
        print("per-car tables:", ", ".join(per_car))
    elif cmd == "port":
        args = sys.argv[2:]
        port(use_zips([a for a in args if not a.startswith("--")]), keep_plates="--keep-plates" in args)
    elif cmd == "names":
        names_command(sys.argv[2:])
    elif cmd == "upgrade-strings":
        from batch_port import azimuth_running
        if azimuth_running():
            sys.exit("close Forza Horizon 2 first")
        upgrade_strings_command()
    elif cmd == "paths":
        # what fh3port.ini resolves to (FH2 Mod Studio shows and edits these)
        print(json.dumps({"game": GAME, "fh3": os.path.dirname(FH3) if FH3 else "", "converter": CLI,
                          "fh3_extra": ";".join(EXTRA_MEDIA),
                          "game_ok": os.path.exists(FH2_DB), "fh3_ok": os.path.exists(FH3_DB), "converter_ok": os.path.exists(CLI),
                          "fh3_extra_ok": all(os.path.isdir(x) for x in EXTRA_MEDIA),
                          "fh3_cars": len(fh3_car_zips())}))
    elif cmd == "restore":
        restore()
    elif cmd == "status":
        print(json.dumps(journal(), indent=1)[:6000])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
