"""DLC and Porsche Pack car synthesizer for FH2.

Synthesizes database rows and metadata for cars present in FH3's media/cars/*.zip
archives that are missing from the base stripped/gamedbRC.slt database:

1) 12 Porsche / SLR cars whose full database rows already exist in FH2's database
   (from FH2's Porsche Expansion DLC): their database definitions are reused as-is.
2) 17 DLC cars not in FH2's database: their database definitions (Data_Car, Data_CarBody,
   List_UpgradeCarBody, List_UpgradeEngine, List_UpgradeDrivetrain, List_UpgradeTireCompound,
   Data_Car_Buckets, and List_SpringDamperPhysics) are synthesized from donor vehicles
   with matching manufacturer, platform, and drivetrain.
"""
import os
import sqlite3

# 12 cars already present in FH2's native database:
# (media_name: FH2 car id)
FH2_EXISTING_DLC = {
    "por_911gt2_12": 1539,
    "por_911gt3rs_12": 2297,
    "por_911turbo_82": 265,
    "por_911turbos_14": 2289,
    "por_918spyder_14": 2290,
    "por_944turbo_89": 268,
    "por_959_87": 269,
    "por_carreragt_03": 292,
    "por_cayenne_12": 1542,
    "por_caymangts_15": 2293,
    "por_mecanturbo_15": 2295,
    "mer_slr_05": 447,
}

# 17 cars synthesized from donor vehicles:
# media_name: (new_id, donor_id, model_short, year, make_id, make_name)
SYNTH_DONORS = {
    "por_356a_56": (2299, 265, "356A Speedster", 1956, 39, "_&857972692"),
    "por_550aspyder_56": (1281, 265, "550 Spyder", 1956, 39, "_&857972692"),
    "por_996gt3_04": (262, 2297, "911 GT3 (996)", 2004, 39, "_&857972692"),
    "ast_db11_17": (2527, 1636, "DB11", 2017, 2, "_&857975174"),
    "bmw_507_59": (1508, 1269, "507", 1959, 6, "_&857975686"),
    "cad_atsv_16": (2262, 1490, "ATS-V", 2016, 8, "_&857975942"),
    "che_vega_71": (1614, 289, "Vega GT", 1971, 9, "_&857975814"),
    "dod_dartgt_13": (2104, 1204, "Dart GT", 2013, 11, "_&857938900"),
    "fer_599xx_10": (1171, 1570, "599XX", 2010, 13, "_&857938644"),
    "hol_commodorevk_85": (2584, 289, "HDT VK Commodore Group A", 1985, 9, "_&857975814"),
    "hon_civictyper_15": (2163, 302, "Civic Type R", 2015, 16, "_&857938004"),
    "hon_s800_70": (2205, 302, "S800", 1970, 16, "_&857938004"),
    "lol_6_t70_69": (2423, 355, "#6 Penske Sunoco T70 MkIIIB", 1969, 9, "_&857975814"),
    "ren_alpinegtalemans_90": (2426, 1204, "GTA Le Mans", 1990, 41, "_&857955285"),
    "sub_75_wrxstivt15r_16": (2716, 1323, "#75 WRX STI VT15r", 2016, 48, "_&857956181"),
    "vau_corsavxr_16": (2427, 1490, "Corsa VXR", 2016, 51, "_&857938901"),
    "vol_242turbo_83": (1299, 642, "242 Turbo Evolution", 1983, 53, "_&857938645"),
}


def is_dlc_car(media_name):
    m = media_name.lower()
    return m in FH2_EXISTING_DLC or m in SYNTH_DONORS


def all_synth_cars(fh2_db_path):
    """Returns a dict of {media_name.lower(): Data_Car dict} for all 29 DLC cars."""
    if not os.path.exists(fh2_db_path):
        return {}
    conn = sqlite3.connect(fh2_db_path)
    conn.row_factory = sqlite3.Row
    c_cols = [c[1] for c in conn.execute("PRAGMA table_info(Data_Car)").fetchall()]
    out = {}

    # 1. Existing in FH2
    for media, car_id in FH2_EXISTING_DLC.items():
        row = conn.execute("SELECT * FROM Data_Car WHERE Id = ?", (car_id,)).fetchone()
        if row:
            d = dict(row)
            out[media] = d

    # 2. Synthesized from donors
    for media, (new_id, donor_id, model_short, year, make_id, make_name) in SYNTH_DONORS.items():
        d_row = conn.execute("SELECT * FROM Data_Car WHERE Id = ?", (donor_id,)).fetchone()
        if d_row:
            d = dict(d_row)
            d["Id"] = new_id
            d["MediaName"] = media.upper()
            d["ModelShort"] = model_short
            d["DisplayName"] = model_short
            if "Year" in c_cols:
                d["Year"] = year
            d["MakeID"] = make_id
            d["MakeName"] = make_name
            d["IsPurchased"] = 1
            d["IsInstalled"] = 1
            out[media] = d

    conn.close()
    return out


def synthesize_car_db(porter, media_name):
    """Inserts or updates the database rows in porter.fh2 for the specified DLC car."""
    m = media_name.lower()
    db = porter.fh2

    if m in FH2_EXISTING_DLC:
        car_id = FH2_EXISTING_DLC[m]
        db.execute("UPDATE Data_Car SET IsPurchased = 1, IsInstalled = 1 WHERE Id = ?", (car_id,))
        return car_id

    if m in SYNTH_DONORS:
        new_id, donor_id, model_short, year, make_id, make_name = SYNTH_DONORS[m]
        new_body = new_id * 1000
        donor_body = donor_id * 1000

        # Clear any existing rows for new_id
        db.execute("DELETE FROM Data_Car WHERE Id = ?", (new_id,))
        db.execute("DELETE FROM Data_CarBody WHERE Id = ?", (new_body,))
        db.execute("DELETE FROM List_UpgradeCarBody WHERE Ordinal = ?", (new_id,))
        db.execute("DELETE FROM List_UpgradeEngine WHERE Ordinal = ?", (new_id,))
        db.execute("DELETE FROM List_UpgradeDrivetrain WHERE Ordinal = ?", (new_id,))
        db.execute("DELETE FROM List_UpgradeTireCompound WHERE Ordinal = ?", (new_id,))
        db.execute("DELETE FROM Data_Car_Buckets WHERE CarId = ?", (new_id,))
        if "List_SpringDamperPhysics" in porter.t2:
            db.execute("DELETE FROM List_SpringDamperPhysics WHERE Ordinal = ?", (new_id,))

        # 1. Data_Car
        c_cols = [c[1] for c in db.execute("PRAGMA table_info(Data_Car)").fetchall()]
        d_row = list(db.execute("SELECT * FROM Data_Car WHERE Id = ?", (donor_id,)).fetchone())
        d_row[c_cols.index("Id")] = new_id
        d_row[c_cols.index("MediaName")] = media_name
        d_row[c_cols.index("ModelShort")] = model_short
        d_row[c_cols.index("DisplayName")] = model_short
        if "Year" in c_cols:
            d_row[c_cols.index("Year")] = year
        d_row[c_cols.index("MakeID")] = make_id
        d_row[c_cols.index("MakeName")] = make_name
        d_row[c_cols.index("IsPurchased")] = 1
        d_row[c_cols.index("IsInstalled")] = 1
        sql = "INSERT INTO Data_Car VALUES (" + ",".join("?" * len(d_row)) + ")"
        db.execute(sql, d_row)

        # 2. Data_CarBody
        b_cols = [c[1] for c in db.execute("PRAGMA table_info(Data_CarBody)").fetchall()]
        b_row = list(db.execute("SELECT * FROM Data_CarBody WHERE Id = ?", (donor_body,)).fetchone())
        b_row[b_cols.index("Id")] = new_body
        db.execute("INSERT INTO Data_CarBody VALUES (" + ",".join("?" * len(b_row)) + ")", b_row)

        # 3. List_UpgradeCarBody
        ucb_cols = [c[1] for c in db.execute("PRAGMA table_info(List_UpgradeCarBody)").fetchall()]
        ucb_row = list(db.execute("SELECT * FROM List_UpgradeCarBody WHERE Ordinal = ? AND IsStock = 1", (donor_id,)).fetchone())
        ucb_row[ucb_cols.index("Id")] = new_body
        ucb_row[ucb_cols.index("Ordinal")] = new_id
        ucb_row[ucb_cols.index("CarBodyID")] = new_body
        db.execute("INSERT INTO List_UpgradeCarBody VALUES (" + ",".join("?" * len(ucb_row)) + ")", ucb_row)

        # 4. List_UpgradeEngine
        ue_cols = [c[1] for c in db.execute("PRAGMA table_info(List_UpgradeEngine)").fetchall()]
        ue_row = list(db.execute("SELECT * FROM List_UpgradeEngine WHERE Ordinal = ? AND IsStock = 1", (donor_id,)).fetchone())
        ue_row[ue_cols.index("Id")] = new_body
        ue_row[ue_cols.index("Ordinal")] = new_id
        db.execute("INSERT INTO List_UpgradeEngine VALUES (" + ",".join("?" * len(ue_row)) + ")", ue_row)

        # 5. List_UpgradeDrivetrain
        ud_cols = [c[1] for c in db.execute("PRAGMA table_info(List_UpgradeDrivetrain)").fetchall()]
        ud_row = list(db.execute("SELECT * FROM List_UpgradeDrivetrain WHERE Ordinal = ? AND IsStock = 1", (donor_id,)).fetchone())
        ud_row[ud_cols.index("Id")] = new_body
        ud_row[ud_cols.index("Ordinal")] = new_id
        db.execute("INSERT INTO List_UpgradeDrivetrain VALUES (" + ",".join("?" * len(ud_row)) + ")", ud_row)

        # 6. List_UpgradeTireCompound
        ut_cols = [c[1] for c in db.execute("PRAGMA table_info(List_UpgradeTireCompound)").fetchall()]
        for r in db.execute("SELECT * FROM List_UpgradeTireCompound WHERE Ordinal = ?", (donor_id,)).fetchall():
            r = list(r)
            r[ut_cols.index("Ordinal")] = new_id
            db.execute("INSERT OR IGNORE INTO List_UpgradeTireCompound VALUES (" + ",".join("?" * len(r)) + ")", r)

        # 7. Data_Car_Buckets
        cb_cols = [c[1] for c in db.execute("PRAGMA table_info(Data_Car_Buckets)").fetchall()]
        for r in db.execute("SELECT * FROM Data_Car_Buckets WHERE CarId = ?", (donor_id,)).fetchall():
            r = list(r)
            r[cb_cols.index("CarId")] = new_id
            db.execute("INSERT OR IGNORE INTO Data_Car_Buckets VALUES (" + ",".join("?" * len(r)) + ")", r)

        # 8. List_SpringDamperPhysics
        if "List_SpringDamperPhysics" in porter.t2:
            sp_cols = [c[1] for c in db.execute("PRAGMA table_info(List_SpringDamperPhysics)").fetchall()]
            for r in db.execute("SELECT * FROM List_SpringDamperPhysics WHERE Ordinal = ?", (donor_id,)).fetchall():
                r = list(r)
                r[sp_cols.index("Ordinal")] = new_id
                db.execute("INSERT OR IGNORE INTO List_SpringDamperPhysics VALUES (" + ",".join("?" * len(r)) + ")", r)

        return new_id

    raise ValueError("Unknown DLC car: %s" % media_name)
