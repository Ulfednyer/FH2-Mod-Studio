"""Body-part removal upgrades: makes car meshes disappear while a removal upgrade (hood, bumpers, side skirts,
rear wing) is fitted.

Why the database alone is not enough: a car's .carbin draws its meshes from two kinds of parts.
  * plain parts (type 2 = body, 4 = brakes, 43 = wheels): every model is always drawn;
  * upgradable parts, one per shop part type (id = UpgradeTypes.PartEnum: 9 rear wing, 34 front bumper, 35 rear
    bumper, 36 hood, 37 side skirts, 41 roll cage): a list of upgrade entries plus models, each model tagged with
    the upgrade row Ids (List_Upgrade*.Id) it is drawn for.
The game draws a tagged model only when the installed row's Id is in its list, so a new row Id (the removal level)
hides every tagged model of that part. That is why a rear-wing removal works on the Gallardo (its wing is tagged to
the stock row) while hood, rear bumper and side skirts don't: those meshes sit in the always-drawn body part. Across
FH2's cars the hood is a body-part mesh 476 times and a tagged one 134 times.

FH2's own removal rows (level 4, RequiresGraphics 0, e.g. POR_911GT2_95's wing row 261004) work the same way: no
upgrade entry, no model tagged with their Id.

The fix moves the chosen body-part meshes into the upgradable part, tagged with every row Id of that part except the
removal rows (a part the car lacks is created with entries for its other rows).
Each run rebuilds from the car's original .carbin, so changing the mesh choice or removing the upgrade never stacks.

Upgrade entry (v3): u16 ver | u8 level | u8 isStock | u32 row Id | u32 body row Id (List_UpgradeCarBody.Id, -1 for
the rear wing, which is keyed by car) | u8 | 2 x vec4 bounds (min, max; FLT_MAX/-FLT_MAX when it draws nothing).

Usage: py bodyparts.py list <MediaName>                 JSON: meshes of the car and suggested meshes per part
       py bodyparts.py apply <MediaName> <spec.json>    rebuild the .carbin; spec {"parts": [...]} (see apply())
       py bodyparts.py restore <MediaName>              put the original .carbin back
       py bodyparts.py make <List_CarMake.ID>           JSON: the make's part manufacturer (or name + decal)
FH2 must be closed (the game keeps car zips open). The first change backs the whole car zip up through the porter's
journal (fh3port.py restore puts it back).
"""
import hashlib
import json
import os
import re
import struct
import sys
import zipfile

import carbin as C

PARTS = {"rear_wing": 9, "front_bumper": 34, "rear_bumper": 35, "hood": 36, "side_skirts": 37}

# meshes suggested per part, by model name (without _a / _race / __slod suffixes); FH2's own upgradable parts hold
# these names (scan of every FH2 car)
SUGGEST = {
    "hood": [r"hood"],
    "front_bumper": [r"bumperf", r"glassbumperf", r"foglight", r"glassfoglight"],
    "rear_bumper": [r"bumperr", r"glassbumperr", r"plate"],
    "side_skirts": [r"skirt"],
    "rear_wing": [r"wing(?!mirror)", r"glasschmsl", r"taillightchmsl", r"glassctl", r"taillightc_"],
}
NO_BOUNDS = struct.pack("<8f", 3.4028234663852886e38, 3.4028234663852886e38, 3.4028234663852886e38, 0.0,
                        -3.4028234663852886e38, -3.4028234663852886e38, -3.4028234663852886e38, 0.0)
FIXED_TYPES = (4, 43)   # brakes and wheels are never moved


def model_name(path):
    return path.replace("/", "\\").rsplit("\\", 1)[-1].lower()


# ───────────── .carbin structure (raw model bytes kept as they are) ─────────────

def parse(d):
    r = C.Reader(d)
    s = {}
    v = r.u16()
    start = 0
    if v >= 3: r.take(16)
    if v >= 5: r.u8()
    r.u32(); r.s(); r.s()
    if v >= 2: r.u16()
    s["ver"] = v
    s["head"] = d[start:r.p]
    s["parts"] = []
    for _ in range(r.count()):
        p = {"type": r.u8() if v >= 4 else None, "ver": r.u16(), "id": r.u32(), "models": []}
        for _ in range(r.count()):
            a = r.p
            name = C.model(r)
            p["models"].append((name, d[a:r.p]))
        p["tail"] = r.take(32) if p["ver"] >= 2 else b""
        s["parts"].append(p)
    s["uparts"] = []
    for _ in range(r.count()):
        u = {"ver": r.u16(), "id": r.u32(), "upgrades": [], "models": []}
        for _ in range(r.count()):
            g = {"ver": r.u16()}
            g["level"], g["stock"], g["row"], g["body"], g["flag"] = r.u8(), r.u8(), r.u32(), r.u32(), r.u8()
            g["models"] = []
            if g["ver"] < 3:
                for _ in range(r.count()):
                    a = r.p
                    name = C.model(r)
                    g["models"].append((name, d[a:r.p]))
            g["tail"] = r.take(32) if g["ver"] >= 2 else b""
            u["upgrades"].append(g)
        if u["ver"] >= 3:
            for _ in range(r.count()):
                ids = [r.u32() for _ in range(r.count())]
                a = r.p
                name = C.model(r)
                u["models"].append((ids, name, d[a:r.p]))
        s["uparts"].append(u)
    if r.p != len(d):
        raise C.Fail("%d trailing bytes" % (len(d) - r.p))
    return s


def to_v3(u):
    """Older upgradable parts keep models inside each upgrade; v3 tags them with row Ids instead."""
    if u["ver"] >= 3:
        return
    for g in u["upgrades"]:
        for name, raw in g["models"]:
            u["models"].append(([g["row"]], name, raw))
        g["models"] = []
        g["ver"] = 3
        g["tail"] = g["tail"] or NO_BOUNDS
    u["ver"] = 3


def serialize(s):
    out = bytearray(s["head"])
    out += struct.pack("<I", len(s["parts"]))
    for p in s["parts"]:
        if s["ver"] >= 4:
            out.append(p["type"])
        out += struct.pack("<HII", p["ver"], p["id"], len(p["models"]))
        for _, raw in p["models"]:
            out += raw
        out += p["tail"]
    out += struct.pack("<I", len(s["uparts"]))
    for u in s["uparts"]:
        out += struct.pack("<HII", u["ver"], u["id"], len(u["upgrades"]))
        for g in u["upgrades"]:
            out += struct.pack("<HBBIIB", g["ver"], g["level"], g["stock"], g["row"], g["body"], g["flag"])
            if g["ver"] < 3:
                out += struct.pack("<I", len(g["models"]))
                for _, raw in g["models"]:
                    out += raw
            out += g["tail"]
        if u["ver"] >= 3:
            out += struct.pack("<I", len(u["models"]))
            for ids, _, raw in u["models"]:
                out += struct.pack("<I", len(ids)) + b"".join(struct.pack("<I", i) for i in ids) + raw
    return bytes(out)


def body_bounds(s):
    for p in s["parts"]:
        if p["type"] not in FIXED_TYPES and p["tail"]:
            return p["tail"]
    return NO_BOUNDS


def apply_parts(d, parts):
    """d: original .carbin; parts: [{"part": key, "body": body row Id or -1, "rows": [[id, level, stock,
    requiresGraphics], ...] (every DB row of that part), "models": [model file names to hide]}] -> (new .carbin,
    report). Rows with RequiresGraphics 0 are removals. Other rows the .carbin doesn't know (a level added as a copy of
    another) get the models of the known row with the nearest level - without that the part vanishes at that level."""
    s = parse(d)
    bounds = body_bounds(s)
    report = []
    for spec in parts:
        pid = PARTS[spec["part"]]
        rows = [(int(r[0]), int(r[1]), int(r[2]), int(r[3]) if len(r) > 3 else 1) for r in spec.get("rows", [])]
        removal = {i for i, _, _, gfx in rows if gfx == 0} | {int(x) for x in spec.get("removal", [])}
        body = int(spec.get("body", -1)) & 0xFFFFFFFF
        want = {m.lower() for m in spec.get("models", [])} if removal else set()
        u = next((x for x in s["uparts"] if x["id"] == pid), None)
        if u is None:
            if not removal:
                continue    # nothing tagged, nothing to hide: every row draws the same body-part meshes
            u = {"ver": 3, "id": pid, "upgrades": [], "models": []}
            s["uparts"].append(u)
        to_v3(u)
        if u["upgrades"]:
            body = u["upgrades"][0]["body"]
        known = list(u["upgrades"])
        have = {g["row"] for g in known}
        copied = []
        # removal rows get no entry, like FH2's own (POR_911GT2_95 wing row 261004): an Id no model is tagged with
        for i, lv, st, _ in rows:
            if i in have or i in removal:
                continue
            src = min(known, key=lambda g: (abs(g["level"] - lv), g["level"]), default=None)
            if src is not None:
                u["upgrades"].append(dict(src, level=lv & 0xFF, stock=st & 0xFF, row=i))
                u["models"] = [(ids + [i] if src["row"] in ids else ids, n, raw) for ids, n, raw in u["models"]]
                copied.append([i, src["row"]])
            else:
                u["upgrades"].append({"ver": 3, "level": lv & 0xFF, "stock": st & 0xFF, "row": i, "body": body,
                                      "flag": 1, "models": [], "tail": bounds})
            have.add(i)
        keep = sorted(have - removal)
        moved = []
        for p in s["parts"]:
            if p["type"] in FIXED_TYPES:
                continue
            stay = []
            for name, raw in p["models"]:
                if model_name(name) in want:
                    u["models"].append((keep, name, raw))
                    moved.append(model_name(name))
                else:
                    stay.append((name, raw))
            p["models"] = stay
        # meshes already tagged in this part (e.g. the Gallardo's wing) are hidden by the new row Id on their own
        tagged = [model_name(n) for ids, n, _ in u["models"] if not removal & set(ids) and model_name(n) in want
                  and model_name(n) not in moved]
        report.append({"part": spec["part"], "moved": moved, "already_tagged": tagged, "visible_for": keep,
                       "removal": sorted(removal), "copied_rows": copied})
    return serialize(s), report


# ───────────── car zips ─────────────

def _porter():
    import fh3port
    return fh3port


def car_zip(media):
    fp = _porter()
    p = os.path.join(fp.MOUNT, "media", "cars", media + ".zip")
    if not os.path.exists(p):
        raise SystemExit("car zip not found: " + p)
    return p


def read_carbin(zp):
    with zipfile.ZipFile(zp) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".carbin")), None)
        if not name:
            raise SystemExit("no .carbin in " + zp)
        return name, z.read(name)


def state_paths(media):
    d = os.path.join(_porter().BACKUP, "bodyparts")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, media + ".carbin"), os.path.join(d, media + ".json")


def original(media, current):
    """The car's own .carbin: the saved copy while the zip still holds what we wrote, else the zip's (first run, or
    the car was re-ported / replaced since)."""
    orig_p, st_p = state_paths(media)
    sha = hashlib.sha1(current).hexdigest()
    if os.path.exists(orig_p) and os.path.exists(st_p):
        with open(st_p, encoding="utf-8") as f:
            if json.load(f).get("written") == sha:
                with open(orig_p, "rb") as g:
                    return g.read()
    with open(orig_p, "wb") as f:
        f.write(current)
    with open(st_p, "w", encoding="utf-8") as f:
        json.dump({"written": sha}, f)
    return current


def write_carbin(media, zp, name, data):
    fp = _porter()
    j = fp.journal()
    fp.replace_in_zip(j, zp, {name: data})
    fp.save_journal(j)
    _, st_p = state_paths(media)
    with open(st_p, "w", encoding="utf-8") as f:
        json.dump({"written": hashlib.sha1(data).hexdigest()}, f)


def cmd_list(media):
    zp = car_zip(media)
    _, cur = read_carbin(zp)
    s = parse(original(media, cur))
    static = []
    for p in s["parts"]:
        if p["type"] not in FIXED_TYPES:
            static += [model_name(n) for n, _ in p["models"]]
    tagged = {str(u["id"]): sorted({model_name(n) for _, n, _ in u["models"]}) for u in s["uparts"]}

    def stem(m):
        return re.sub(r"(__slod)?\.modelbin$", "", m)

    suggest = {k: sorted(m for m in static if any(re.match(p, stem(m)) for p in pats)) for k, pats in SUGGEST.items()}
    print(json.dumps({"meshes": sorted(set(static)), "tagged": tagged, "suggest": suggest, "parts": PARTS}))


def cmd_apply(media, spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    zp = car_zip(media)
    name, cur = read_carbin(zp)
    orig = original(media, cur)
    parts = [p for p in spec.get("parts", []) if p.get("rows")]
    new, report = apply_parts(orig, parts)
    if new == orig:
        return cmd_restore(media)
    parse(new)   # must read back exactly
    if new == cur:
        print(json.dumps({"changed": False, "report": report}))
        return
    write_carbin(media, zp, name, new)
    print(json.dumps({"changed": True, "report": report}))


def cmd_restore(media):
    zp = car_zip(media)
    name, cur = read_carbin(zp)
    orig_p, st_p = state_paths(media)
    orig = original(media, cur)
    if orig != cur:
        write_carbin(media, zp, name, orig)
        print(json.dumps({"changed": True, "restored": True}))
    else:
        print(json.dumps({"changed": False, "restored": True}))
    for p in (orig_p, st_p):
        if os.path.exists(p):
            os.remove(p)


def cmd_make(make_id):
    """The List_PartManufacturer row of a car make (matched by English name), so removal parts show the car's own
    brand like FH2's (POR_911GT2_95's wing removal: Porsche). Makes without one: name + the livery decal of that
    name for a new row (FH2's DLC rows hold plain names too: 'Rocket Bunny', 'RWB')."""
    import sqlite3
    import strtables
    fp = _porter()
    stripped = os.path.join(fp.MOUNT, "media", "stripped")
    db = sqlite3.connect("file:%s?mode=ro" % os.path.join(stripped, "gamedbRC.slt").replace("\\", "/"), uri=True)
    with zipfile.ZipFile(os.path.join(stripped, "stringtables", "EN.zip")) as z:
        names = {n.lower(): n for n in z.namelist()}

        def table(n):
            k = names.get(n.lower())
            return strtables.Lsb2(z.read(k)).strings if k else {}

        pm, mk = table("List_PartManufacturer.str"), table("List_CarMake.str")

    def text(tab, v):
        if isinstance(v, str) and v.startswith("_&") and v[2:].isdigit():
            return tab.get(int(v[2:]) & 0xFFFF)
        return v

    row = db.execute("SELECT DisplayName, IconPathBase FROM List_CarMake WHERE ID = ?", (int(make_id),)).fetchone()
    if not row:
        print(json.dumps({"name": None}))
        return
    name = (text(mk, row[0]) or row[1] or "").strip()
    key = name.lower()
    part = next((i for i, v in db.execute("SELECT Id, PartManufacturer FROM List_PartManufacturer")
                 if (text(pm, v) or "").strip().lower() == key), None)
    decal = next((os.path.splitext(os.path.basename(f.replace("\\", "/")))[0]
                  for f, a in db.execute("SELECT Filename, AlphaSort FROM Livery_Decals")
                  if (a or "").strip().lower() == key), None)
    print(json.dumps({"name": name, "part_manufacturer": part, "decal": decal}))


def main(argv):
    if len(argv) >= 2 and argv[0] == "list":
        cmd_list(argv[1])
    elif len(argv) >= 2 and argv[0] == "make":
        cmd_make(argv[1])
    elif len(argv) >= 3 and argv[0] == "apply":
        cmd_apply(argv[1], argv[2])
    elif len(argv) >= 2 and argv[0] == "restore":
        cmd_restore(argv[1])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
