"""Generates FH2ModStudio/Core/DriftDragPack.Data.cs: the SQL that gives every car drag tyres, drift tyres and a drift
suspension.

Research (2026-10-28, FM7 gamedb outputdbn.slt + FH3 gamedbRC.slt):
- FM7: drag tyres = List_UpgradeTireCompound Level 4, compound 17 '17_DragTire' (group 8 Drag), model 'drag', 10000 CR,
  on 836 of 837 cars. Drift suspension = List_UpgradeSpringDamper Level 5 on 651 cars: the race (Level 3) springs with
  SteerMaxAngle 40 -> 60 (+ filtered 60), steering speeds x1.5, AckermanPercentageMax 0.15, front geometry
  DriftFront.xml (physics type 12), front camber -1 -> -3, rear camber -0.5 -> -1, rear toe -0.05.
- FH3 defines '18_Drift' (low grip, 1.0 vs FH2 road tyres 1.6-1.7) and '19_Drag' compounds (no car uses them); its
  List_TireCompound columns are a superset of FH2's, so both and their friction/affect curves go into FH2 as compounds
  22 / 21 with new curve ids.
- FH2 has no steering columns in List_UpgradeSpringDamper (steering lock is per car in Data_Car); fh2sql.dll raises it
  while the drift suspension is installed. No DriftFront.xml in FH2: the drift suspension carries the alignment
  (front camber -5, rear -1, rear toe -0.05 by default; FH2 Mod Studio appends UPDATEs for the user's values).

The upgrade shop lists a part only when the Upgrades table names its (UpgradeTypes id, level) or has a level -1 wildcard
for the type (shop SQL: Upgrades.Level = PartTable.Level OR Upgrades.Level = -1). Stock FH2 names springs (type 13)
levels 0-4 (Stock/Street/Sport/Race/Rally) and tyres (type 21) 0-5 (..., 4 Drag, 5 Rally). So a new entry for any part =
rows at a fixed level + one Upgrades row for (type, level) whose Name/Description are Upgrades.str string ids
(hash 0x7091, keys free in every language; fh3port.py upgrade-strings writes the texts):
  drag tyres      tyre level 4 (FH2's own "Drag Tire Compound" entry)
  drift suspension spring level 5, Upgrades 274, strings 0xD000/0xD001
  drift tyres     tyre level 6, Upgrades 275, strings 0xD002/0xD003
Marker Ids (Ordinal*1000 + 905 springs / 995 rear physics, 917 drag tyres, 916 drift tyres) keep the script idempotent;
it is saved as a mod that is re-applied on every game start.
usage: py driftdrag_gen.py <FH3 gamedbRC.slt> <FH2 gamedbRC.slt> <out .cs>
"""
import sqlite3
import sys

FC0, MC0, AC0 = 59, 30, 111          # first free FrictionCurveID / FrictionMultiCurveID / AffectCurveID in FH2
DRIFT_PRICE = 2050
OFFROAD_TYPES = "11,12,13,16,17,18,19,33,34"   # rally / off-road geometries: not a base for drift
SPRING_TYPE, TIRE_TYPE = "13", "21"
DRIFT_LEVEL = 5
DRIFT_FRONT_CAMBER, DRIFT_REAR_CAMBER, DRIFT_REAR_TOE = -5.0, -1.0, -0.05
UI = "GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\"


def sid(key):
    return "_&%d" % (0x7091 << 16 | key)


# (FH3 compound, FH2 compound, name, tyre level, marker, price, model, open-wheel model, Upgrades row or None)
TYRES = [
    (19, 21, "21_Drag", 4, 917, 10000, "drag", "OW_drag", None),
    (18, 22, "22_Drift", 6, 916, 8000, "b", "OW_b",
     (275, sid(0xD002), sid(0xD003), UI + "Tire_Rims\\tire_compound_3.swatchbin", UI + "Tire_Rims\\tire_compound_LG_3.swatchbin")),
]
DRIFT_UPGRADE = (274, sid(0xD000), sid(0xD001), UI + "Platform_Handling\\springs_dampers_3.swatchbin",
                 UI + "Platform_Handling\\springs_dampers_LG_3.swatchbin")


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return repr(v)


def cols(db, t):
    return [r[1] for r in db.execute('PRAGMA table_info("%s")' % t)]


def row(db, t, key, kv):
    c = cols(db, t)
    r = db.execute('SELECT * FROM "%s" WHERE "%s" = ?' % (t, key), (kv,)).fetchone()
    return dict(zip(c, r))


def insert(t, columns, values):
    return 'INSERT OR REPLACE INTO %s (%s) VALUES (%s);' % (t, ", ".join(columns), ", ".join(lit(v) for v in values))


def upgrades_row(entry, type_id, level):
    uid, name, desc, icon, image = entry
    return insert("Upgrades", ["id", "TypeId", "IsException", "Name", "Level", "Description", "IconPath", "ImagePath"],
                  [uid, type_id, 0, name, level, desc, icon, image])


class Curves:
    """New FH2 ids for FH3 curves, shared by every imported compound."""

    def __init__(self):
        self.f, self.m, self.a = {}, {}, {}


def import_compound(f3, f2, fh3_id, fh2_id, name, cv, stmts):
    tc = row(f3, "List_TireCompound", "TireCompoundID", fh3_id)
    mc_cols, fc_cols, ac_cols = (cols(f2, t) for t in ("List_TireFrictionMultiCurve", "List_TireFrictionCurve", "List_TireAffectCurve"))
    for key in ("FrictionMultiCurveLateralID", "FrictionMultiCurveLongitudinalAccelID", "FrictionMultiCurveLongitudinalBrakeID"):
        mid = tc[key]
        if mid in cv.m:
            continue
        mc = row(f3, "List_TireFrictionMultiCurve", "FrictionMultiCurveID", mid)
        for fk in ("TireFrictionCurveID0", "TireFrictionCurveID1"):
            fid = mc[fk]
            if fid not in cv.f:
                cv.f[fid] = FC0 + len(cv.f)
                fc = row(f3, "List_TireFrictionCurve", "FrictionCurveID", fid)
                stmts.append(insert("List_TireFrictionCurve", fc_cols, [cv.f[fid] if c == "FrictionCurveID" else fc.get(c) for c in fc_cols]))
        cv.m[mid] = MC0 + len(cv.m)
        stmts.append(insert("List_TireFrictionMultiCurve", mc_cols,
                            [cv.m[mid] if c == "FrictionMultiCurveID" else cv.f[mc[c]] if c in ("TireFrictionCurveID0", "TireFrictionCurveID1")
                             else mc.get(c) for c in mc_cols]))
    tc_cols = cols(f2, "List_TireCompound")
    for key in [c for c in tc_cols if c.startswith("AffectCurve")]:
        aid = tc[key]
        if aid not in cv.a:
            cv.a[aid] = AC0 + len(cv.a)
            ac = row(f3, "List_TireAffectCurve", "AffectCurveID", aid)
            stmts.append(insert("List_TireAffectCurve", ac_cols, [cv.a[aid] if c == "AffectCurveID" else ac.get(c) for c in ac_cols]))
    vals = []
    for c in tc_cols:
        v = tc[c]
        if c == "TireCompoundID":
            v = fh2_id
        elif c == "DisplayName":
            v = name
        elif c.startswith("FrictionMultiCurve"):
            v = cv.m[v]
        elif c.startswith("AffectCurve"):
            v = cv.a[v]
        vals.append(v)
    stmts.append(insert("List_TireCompound", tc_cols, vals))


def tyre_slot(compound, level, marker, price, model, ow_model, stmts):
    """Every car gets the compound at a fixed tyre level: a non-stock row already there (FH3 ports put race compounds at
    4, off-road at 6) becomes it, cars without one get a new row. Open-wheel cars keep open-wheel models."""
    pick = ("CASE WHEN (SELECT s.TireModelName FROM List_UpgradeTireCompound s WHERE s.Ordinal = %s AND s.IsStock = 1) "
            "LIKE 'OW%%' THEN '%s' ELSE '%s' END")
    stmts.append(
        "UPDATE List_UpgradeTireCompound SET TireCompoundID = %d, Price = %d, TireModelName = %s "
        "WHERE Level = %d AND IsStock = 0 AND TireCompoundID <> %d;"
        % (compound, price, pick % ("List_UpgradeTireCompound.Ordinal", ow_model, model), level, compound))
    stmts.append(
        "INSERT INTO List_UpgradeTireCompound (Id, Ordinal, Level, IsStock, TireCompoundID, ManufacturerID, Price, MassDiff, "
        "DragScale, WindInstabilityScale, RequiresGraphics, TireModelName) "
        "SELECT t.Ordinal * 1000 + %d, t.Ordinal, %d, 0, %d, 0, %d, 0, 1, 1, 1, %s "
        "FROM List_UpgradeTireCompound t WHERE t.IsStock = 1 "
        "AND NOT EXISTS (SELECT 1 FROM List_UpgradeTireCompound x WHERE x.Ordinal = t.Ordinal AND x.Level = %d) "
        "AND NOT EXISTS (SELECT 1 FROM List_UpgradeTireCompound x WHERE x.Id = t.Ordinal * 1000 + %d);"
        % (marker, level, compound, price, pick % ("t.Ordinal", ow_model, model), level, marker))


def main(fh3_path, fh2_path, out):
    f3, f2 = sqlite3.connect(fh3_path), sqlite3.connect(fh2_path)
    stmts = []
    # rows of the first version (next free level: drag tyres at 6, drift at 4 or 5) in a live database
    for _, _, _, level, marker, *_ in TYRES:
        stmts.append("DELETE FROM List_UpgradeTireCompound WHERE Id %% 1000 = %d AND Level <> %d;" % (marker, level))
    stmts.append("DELETE FROM List_UpgradeSpringDamper WHERE Id %% 1000 = 905 AND Level <> %d;" % DRIFT_LEVEL)

    cv = Curves()
    for fh3_id, fh2_id, name, level, marker, price, model, ow_model, upg in TYRES:
        import_compound(f3, f2, fh3_id, fh2_id, name, cv, stmts)
        tyre_slot(fh2_id, level, marker, price, model, ow_model, stmts)
        if upg:
            stmts.append(upgrades_row(upg, TIRE_TYPE, level))

    # drift suspension: physics copied from the car's best adjustable road/race springs (cars without any - off-road,
    # traffic - use their highest level), drift alignment
    ph = cols(f2, "List_SpringDamperPhysics")
    src = ("COALESCE((SELECT u2.Id FROM List_UpgradeSpringDamper u2 JOIN List_SpringDamperPhysics p2 ON p2.SpringDamperPhysicsID = "
           "u2.FrontSpringDamperPhysicsID WHERE u2.Ordinal = u.Ordinal AND p2.MinSpringRate < p2.MaxSpringRate AND "
           "p2.SuspensionPhysicsTypeID NOT IN (%s) ORDER BY u2.Level DESC LIMIT 1), "
           "(SELECT u3.Id FROM List_UpgradeSpringDamper u3 WHERE u3.Ordinal = u.Ordinal AND u3.Id %% 1000 <> 905 "
           "ORDER BY u3.Level DESC LIMIT 1))" % OFFROAD_TYPES)
    for end, new_id, extra in (("Front", "u.Ordinal * 1000 + 905", {"StaticCamber": repr(DRIFT_FRONT_CAMBER)}),
                               ("Rear", "u.Ordinal * 1000 + 995", {"StaticCamber": repr(DRIFT_REAR_CAMBER), "StaticToe": repr(DRIFT_REAR_TOE)})):
        sel = ", ".join(new_id if c == "SpringDamperPhysicsID" else extra.get(c, "p." + c) for c in ph)
        stmts.append(
            "INSERT INTO List_SpringDamperPhysics (%s) SELECT %s FROM List_UpgradeSpringDamper u JOIN List_SpringDamperPhysics p "
            "ON p.SpringDamperPhysicsID = u.%sSpringDamperPhysicsID WHERE u.Id = %s "
            "AND NOT EXISTS (SELECT 1 FROM List_SpringDamperPhysics x WHERE x.SpringDamperPhysicsID = %s);"
            % (", ".join(ph), sel, end, src, new_id))
    us = cols(f2, "List_UpgradeSpringDamper")
    fixed = {"Id": "u.Ordinal * 1000 + 905", "Level": str(DRIFT_LEVEL), "IsStock": "0", "Price": str(DRIFT_PRICE),
             "FrontSpringDamperPhysicsID": "u.Ordinal * 1000 + 905", "RearSpringDamperPhysicsID": "u.Ordinal * 1000 + 995"}
    stmts.append(
        "INSERT INTO List_UpgradeSpringDamper (%s) SELECT %s FROM List_UpgradeSpringDamper u WHERE u.Id = %s "
        "AND EXISTS (SELECT 1 FROM List_SpringDamperPhysics x WHERE x.SpringDamperPhysicsID = u.Ordinal * 1000 + 905) "
        "AND NOT EXISTS (SELECT 1 FROM List_UpgradeSpringDamper x WHERE x.Id = u.Ordinal * 1000 + 905) "
        "AND NOT EXISTS (SELECT 1 FROM List_UpgradeSpringDamper x WHERE x.Ordinal = u.Ordinal AND x.Level = %d);"
        % (", ".join(us), ", ".join(fixed.get(c, "u." + c) for c in us), src, DRIFT_LEVEL))
    stmts.append(upgrades_row(DRIFT_UPGRADE, SPRING_TYPE, DRIFT_LEVEL))
    # alignment always set (rows from an earlier version keep theirs otherwise); FH2 Mod Studio appends the user's values
    stmts.append("UPDATE List_SpringDamperPhysics SET StaticCamber = %r WHERE SpringDamperPhysicsID %% 1000 = 905;" % DRIFT_FRONT_CAMBER)
    stmts.append("UPDATE List_SpringDamperPhysics SET StaticCamber = %r, StaticToe = %r WHERE SpringDamperPhysicsID %% 1000 = 995;"
                 % (DRIFT_REAR_CAMBER, DRIFT_REAR_TOE))

    sql = "\n".join(stmts)
    cs = ("// Generated by research/modstudio/driftdrag_gen.py - do not edit by hand.\n"
          "namespace FH2ModStudio.Core;\n\npublic static partial class DriftDragPack\n{\n"
          "    public const int DragCompound = %d, DriftCompound = %d, DragLevel = %d, DriftTyreLevel = %d, DriftLevel = %d;\n"
          "    public const string Sql = @\"%s\";\n}\n"
          % (TYRES[0][1], TYRES[1][1], TYRES[0][3], TYRES[1][3], DRIFT_LEVEL, sql.replace('"', '""')))
    open(out, "w", encoding="utf-8").write(cs)
    print("%d statements, %d friction curves, %d multi curves, %d affect curves" % (len(stmts), len(cv.f), len(cv.m), len(cv.a)))


if __name__ == "__main__":
    main(*sys.argv[1:4])
