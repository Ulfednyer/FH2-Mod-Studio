using System.Globalization;
using System.Text;

namespace FH2ModStudio.Core;

public enum UpgradeKind { Aspiration, EngineSwap, DrivetrainSwap, TireCompound, TireWidth, Spacers, ExtraLevel, BodyPart }

public sealed record Donor(string Key, string Title, string Detail, double Score, bool Recommended);

/// <summary>
/// Builds new upgrade rows. Rows follow the game's scheme: Id = key × 1000 + n, IsStock = 0, next free Level,
/// values copied from a donor so the game sees a complete, consistent part.
/// </summary>
public static class Upgrades
{
    public static readonly (string Table, string Label)[] AspirationParts =
    {
        ("List_UpgradeEngineTurboSingle", "Single turbo"),
        ("List_UpgradeEngineTurboTwin", "Twin turbo"),
        ("List_UpgradeEngineTurboQuad", "Quad turbo"),
        ("List_UpgradeEngineCSC", "Centrifugal supercharger"),
        ("List_UpgradeEngineDSC", "Positive-displacement supercharger"),
    };

    private static string Q(string ident) => DbHistory.QuoteIdent(ident);
    private static string F(double v) => v.ToString("0.###", CultureInfo.InvariantCulture);

    private static long? Scalar(ICarDb db, string sql) =>
        db.Query(sql, out _) is { Rows.Count: > 0 } r && long.TryParse(r.Rows[0][0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) ? v : null;

    private static double Num(string? s) => double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0;

    /// <summary>Next free Id in [baseId, baseId + 999], skipping ids already handed out in this batch.</summary>
    private static long NextId(ICarDb db, string table, long baseId, HashSet<long> taken)
    {
        var max = Scalar(db, $"SELECT MAX(Id) FROM {Q(table)} WHERE Id >= {baseId} AND Id < {baseId + 1000};") ?? baseId - 1;
        long id = Math.Max(max + 1, baseId);
        while (taken.Contains(id)) id++;
        if (id >= baseId + 1000) throw new InvalidOperationException("No free id left for this part.");
        taken.Add(id);
        return id;
    }

    private static int MaxLevel(ICarDb db, string table, string keyColumn, long key) =>
        (int)(Scalar(db, $"SELECT MAX(Level) FROM {Q(table)} WHERE {Q(keyColumn)} = {key};") ?? -1);

    // ───────────── shop slots ─────────────

    /// <summary>
    /// The upgrade shop shows a part by its Level: every level is a fixed slot (street, sport, race, ...).
    /// These are the slot ranges the stock database uses. A row outside the range is loaded but the shop
    /// never shows it, and these tables hold at most one row per level and car.
    /// </summary>
    private static readonly Dictionary<string, (int Min, int Max)> Slots = new(StringComparer.Ordinal)
    {
        ["List_UpgradeEngineCamshaft"] = (0, 3), ["List_UpgradeEngineValves"] = (0, 3), ["List_UpgradeEngineDisplacement"] = (0, 3),
        ["List_UpgradeEnginePistonsCompression"] = (0, 3), ["List_UpgradeEngineFuelSystem"] = (0, 3), ["List_UpgradeEngineIgnition"] = (0, 3),
        ["List_UpgradeEngineExhaust"] = (0, 3), ["List_UpgradeEngineIntake"] = (0, 3), ["List_UpgradeEngineFlywheel"] = (0, 3),
        ["List_UpgradeEngineOilCooling"] = (0, 3), ["List_UpgradeEngineRestrictorPlate"] = (0, 3),
        ["List_UpgradeEngineManifold"] = (1, 3), ["List_UpgradeEngineIntercooler"] = (1, 3),
        ["List_UpgradeEngineTurboSingle"] = (1, 3), ["List_UpgradeEngineTurboTwin"] = (1, 3), ["List_UpgradeEngineTurboQuad"] = (0, 3),
        ["List_UpgradeEngineCSC"] = (1, 3), ["List_UpgradeEngineDSC"] = (1, 3),
        ["List_UpgradeDrivetrainClutch"] = (0, 3), ["List_UpgradeDrivetrainDifferential"] = (0, 3), ["List_UpgradeDrivetrainDriveline"] = (0, 3),
        ["List_UpgradeDrivetrainTransmission"] = (0, 4),
        ["List_UpgradeCarBodyWeight"] = (0, 3), ["List_UpgradeCarBodyChassisStiffness"] = (0, 3),
        ["List_UpgradeCarBodyTireWidthFront"] = (0, 6), ["List_UpgradeCarBodyTireWidthRear"] = (0, 6),
        ["List_UpgradeSpringDamper"] = (0, 4), ["List_UpgradeAntiSwayFront"] = (0, 3), ["List_UpgradeAntiSwayRear"] = (0, 3),
        ["List_UpgradeBrakes"] = (0, 3), ["List_UpgradeTireCompound"] = (0, 5),
        ["List_UpgradeRearWing"] = (0, 4), ["List_UpgradeCarBodyFrontBumper"] = (0, 4),
        ["List_UpgradeCarBodyRearBumper"] = (0, 4), ["List_UpgradeCarBodySideSkirt"] = (0, 4), ["List_UpgradeCarBodyHood"] = (0, 4),
    };

    public static (int Min, int Max)? SlotRange(string table) => Slots.TryGetValue(table, out var s) ? s : null;

    /// <summary>True when the shop has a slot for this level of the table (tables without fixed slots always pass).</summary>
    public static bool InShop(string table, int level) => SlotRange(table) is not { } s || (level >= s.Min && level <= s.Max);

    private static HashSet<int> UsedLevels(ICarDb db, string table, string keyColumn, long key) =>
        db.Query($"SELECT Level FROM {Q(table)} WHERE {Q(keyColumn)} = {key};", out _)?.Rows.Select(r => (int)Num(r[0])).ToHashSet() ?? new();

    public static List<int> FreeSlots(ICarDb db, string table, string keyColumn, long key)
    {
        if (SlotRange(table) is not { } s) return new();
        var used = UsedLevels(db, table, keyColumn, key);
        return Enumerable.Range(s.Min, s.Max - s.Min + 1).Where(l => !used.Contains(l)).ToList();
    }

    /// <summary>
    /// Copies rows into this car's key, re-numbering Id and marking them non-stock. In slot tables each row
    /// keeps its level and rows whose slot is taken are skipped; elsewhere the rows are stacked above the existing levels.
    /// </summary>
    private static string CloneRows(ICarDb db, string table, string keyColumn, long newKey, long idBase, SqlResult source,
        Func<Dictionary<string, string?>, Dictionary<string, string?>>? adjust = null)
    {
        var taken = new HashSet<long>();
        int levelIdx = source.Columns.IndexOf("Level");
        bool slotted = SlotRange(table) != null;
        var used = UsedLevels(db, table, keyColumn, newKey);
        int existingMax = used.Count > 0 ? used.Max() : -1;
        int sourceMin = levelIdx >= 0 && source.Rows.Count > 0 ? source.Rows.Min(r => (int)Num(r[levelIdx])) : 0;
        var sb = new StringBuilder();
        foreach (var row in source.Rows)
        {
            var values = source.Columns.Select((c, i) => (c, row[i])).ToDictionary(x => x.c, x => x.Item2, StringComparer.OrdinalIgnoreCase);
            values[keyColumn] = newKey.ToString(CultureInfo.InvariantCulture);
            if (values.ContainsKey("IsStock")) values["IsStock"] = "0";
            if (levelIdx >= 0 && !slotted)
            {
                int lvl = (int)Num(row[levelIdx]);
                values["Level"] = (existingMax < sourceMin ? lvl : existingMax + 1 + lvl - sourceMin).ToString(CultureInfo.InvariantCulture);
            }
            if (adjust != null) values = adjust(values);
            if (slotted && levelIdx >= 0)
            {
                int lvl = (int)Num(values["Level"]);
                if (used.Contains(lvl) || !InShop(table, lvl)) continue;
                used.Add(lvl);
            }
            values["Id"] = NextId(db, table, idBase, taken).ToString(CultureInfo.InvariantCulture);
            var targetCols = db.Query($"PRAGMA table_info({Q(table)});", out _)?.Rows.Select(r => r[1]!).ToList() ?? source.Columns;
            var cols = targetCols.Where(c => values.ContainsKey(c)).ToList();
            sb.AppendLine(CarModel.InsertSql(table, cols, cols.Select(c => values[c])));
        }
        if (sb.Length == 0)
            throw new InvalidOperationException("Every shop slot this part would use is already taken on this car - nothing to add. Change the existing levels in the car's sections instead.");
        return sb.ToString();
    }

    // ───────────── turbo / supercharger ─────────────

    public static List<Donor> AspirationDonors(ICarDb db, CarIds ids, string table)
    {
        var mine = db.Query($"SELECT CylinderID, EngineGraphingMaxPower FROM Data_Engine WHERE EngineID = {ids.EngineId};", out _);
        string? cyl = mine?.Rows.FirstOrDefault()?[0];
        double power = Num(mine?.Rows.FirstOrDefault()?[1]);
        string queryTable = table;
        bool isQuadTurbo = table == "List_UpgradeEngineTurboQuad";
        // List_UpgradeEngineTurboQuad has 0 rows in stock game; fallback to twin turbo donors
        if (isQuadTurbo && Scalar(db, "SELECT COUNT(*) FROM List_UpgradeEngineTurboQuad;") == 0)
            queryTable = "List_UpgradeEngineTurboTwin";

        var r = db.Query($"SELECT t.EngineID, MIN(c.MediaName), COUNT(*), e.CylinderID, e.EngineGraphingMaxPower, MAX(t.MaxScale) " +
                         $"FROM {Q(queryTable)} t JOIN Data_Engine e ON e.EngineID = t.EngineID " +
                         $"JOIN List_UpgradeEngine u ON u.EngineID = t.EngineID JOIN Data_Car c ON c.Id = u.Ordinal " +
                         $"WHERE t.EngineID <> {ids.EngineId} GROUP BY t.EngineID;", out _);
        if (r == null) return new();
        var list = r.Rows.Select(row =>
        {
            double p = Num(row[4]);
            long eid = (long)Num(row[0]);
            bool oemQuad = isQuadTurbo && (eid == 788 || eid == 678); // Veyron SS or EB110 SS
            double score = oemQuad ? 0 : (row[3] == cyl ? 0 : 1000) + Math.Abs(p - power) + (isQuadTurbo ? 50 : 0);
            string title = row[1] + (oemQuad ? " [Quad Turbo OEM]" : " engine");
            return new Donor(row[0]!, title, $"{row[2]} level(s) · max boost ×{F(Num(row[5]))} · {Math.Round(p * 1.341)} hp stock", score, oemQuad);
        }).OrderBy(d => d.Score).ToList();
        if (list.Count > 0 && !list.Any(d => d.Recommended)) list[0] = list[0] with { Recommended = true };
        return list;
    }

    public static string BuildAspiration(ICarDb db, CarIds ids, string table, string donorEngine, string mode = "both")
    {
        var sb = new StringBuilder();
        string donorTable = table;
        bool isQuadTurbo = table == "List_UpgradeEngineTurboQuad";
        if (isQuadTurbo)
        {
            sb.Append(EnsureQuadTurboCatalog(db));
            if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeEngineTurboQuad WHERE EngineID = {donorEngine};") == 0)
                donorTable = "List_UpgradeEngineTurboTwin";
        }

        var src = db.Query($"SELECT * FROM {Q(donorTable)} WHERE EngineID = {donorEngine} ORDER BY Level;", out var err)
                  ?? throw new InvalidOperationException(err);
        if (src.Rows.Count == 0)
            throw new InvalidOperationException($"No donor parts found in {donorTable} for engine {donorEngine}.");

        sb.Append(CloneRows(db, table, "EngineID", ids.EngineId!.Value, ids.EngineId.Value * 1000, src));

        // When mode is "direct" or "both", set the engine stock aspiration and car aspiration type to Quad Turbo (4)
        if (isQuadTurbo && (mode == "direct" || mode == "both"))
        {
            sb.AppendLine($"UPDATE Data_Engine SET AspirationID_Stock = 4 WHERE EngineID = {ids.EngineId};");
            sb.AppendLine($"UPDATE Data_Car SET AspirationTypeId = 4 WHERE Id = {ids.CarId};");
        }

        // Ensure List_UpgradeEngineIntercooler rows exist for this engine (needed if engine was NA)
        if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeEngineIntercooler WHERE EngineID = {ids.EngineId};") == 0)
        {
            var icSrc = db.Query($"SELECT * FROM List_UpgradeEngineIntercooler WHERE EngineID = {donorEngine} ORDER BY Level;", out _);
            if (icSrc is { Rows.Count: > 0 })
                sb.Append(CloneRows(db, "List_UpgradeEngineIntercooler", "EngineID", ids.EngineId!.Value, ids.EngineId.Value * 1000, icSrc));
        }

        return sb.ToString();
    }

    // ───────────── engine swap ─────────────

    public static List<Donor> EngineDonors(ICarDb db, CarIds ids)
    {
        var r = db.Query("SELECT e.EngineID, MIN(c.MediaName), cfg.EngineConfig, cy.Number, e.\"EngineMass-kg\", e.EngineGraphingMaxPower, " +
                         "MIN(c.Displacement), asp.Aspiration, e.EngineID IN (SELECT EngineID FROM List_UpgradeEngine WHERE IsStock = 0) " +
                         "FROM Data_Engine e JOIN List_UpgradeEngine u ON u.EngineID = e.EngineID AND u.IsStock = 1 JOIN Data_Car c ON c.Id = u.Ordinal " +
                         "LEFT JOIN List_EngineConfig cfg ON cfg.ConfigID = e.ConfigID LEFT JOIN List_Cylinders cy ON cy.CylinderID = e.CylinderID " +
                         $"LEFT JOIN List_Aspiration asp ON asp.AspirationID = e.AspirationID_Stock WHERE e.EngineID <> {ids.EngineId} GROUP BY e.EngineID;", out _);
        if (r == null) return new();
        return r.Rows.Select(row =>
        {
            bool known = row[8] == "1";
            double hp = Math.Round(Num(row[5]) * 1.341);
            return new Donor(row[0]!, $"{row[1]} engine", $"{row[2]}{row[3]} · {row[6]} cc · {row[7]} · {hp} hp · {F(Num(row[4]))} kg", known ? 0 : 1000 - hp / 10, known);
        }).OrderBy(d => d.Score).ToList();
    }

    public static double EngineMass(ICarDb db, string engineId) =>
        Num(db.Query($"SELECT \"EngineMass-kg\" FROM Data_Engine WHERE EngineID = {engineId};", out _)?.Rows.FirstOrDefault()?[0]);

    public static string BuildEngineSwap(ICarDb db, CarIds ids, string engineId, double price, double massDiff)
    {
        var level = MaxLevel(db, "List_UpgradeEngine", "Ordinal", ids.CarId) + 1;
        var id = NextId(db, "List_UpgradeEngine", ids.CarId * 1000, new HashSet<long>());
        return CarModel.InsertSql("List_UpgradeEngine",
            new[] { "Id", "Ordinal", "Level", "EngineID", "IsStock", "ManufacturerID", "Price", "MassDiff", "WeightDistDiff", "DragScale", "WindInstabilityScale" },
            new[] { id.ToString(CultureInfo.InvariantCulture), ids.CarId.ToString(CultureInfo.InvariantCulture), level.ToString(CultureInfo.InvariantCulture),
                    engineId, "0", "0", F(price), F(massDiff), "0", "1", "1" });
    }

    // ───────────── drivetrain conversion ─────────────

    public static List<Donor> DrivetrainDonors(ICarDb db, CarIds ids, string driveType)
    {
        var r = db.Query("SELECT d.DrivetrainID, MIN(c.MediaName), t.DriveType FROM Data_Drivetrain d JOIN List_DriveType t ON t.ID = d.DrivetypeID " +
                         "JOIN List_UpgradeDrivetrain u ON u.DrivetrainID = d.DrivetrainID AND u.IsStock = 1 JOIN Data_Car c ON c.Id = u.Ordinal " +
                         $"WHERE d.DrivetypeID = {driveType} AND d.DrivetrainID <> {ids.DrivetrainId} GROUP BY d.DrivetrainID ORDER BY 2;", out _);
        var list = r?.Rows.Select(row => new Donor(row[0]!, $"{row[2]} drivetrain from {row[1]}", "gearbox, differential and clutch of that car", 0, false)).ToList() ?? new();
        if (list.Count > 0) list[0] = list[0] with { Recommended = true };
        return list;
    }

    public static string BuildDrivetrainSwap(ICarDb db, CarIds ids, string drivetrainId, string driveType, double price, double massDiff)
    {
        var placement = db.Query($"SELECT EnginePlacementID FROM Data_Car WHERE Id = {ids.CarId};", out _)?.Rows.FirstOrDefault()?[0] ?? "1";
        var powertrain = Scalar(db, $"SELECT Id FROM Powertrains WHERE DrivetrainId = {driveType} AND EnginePlacementId = {placement};") ?? 0;
        var level = MaxLevel(db, "List_UpgradeDrivetrain", "Ordinal", ids.CarId) + 1;
        var id = NextId(db, "List_UpgradeDrivetrain", ids.CarId * 1000, new HashSet<long>());
        return CarModel.InsertSql("List_UpgradeDrivetrain",
            new[] { "Id", "Ordinal", "DrivetrainID", "PowertrainId", "MassDiff", "WeightDistDiff", "Level", "ManufacturerId", "Price", "IsStock" },
            new[] { id.ToString(CultureInfo.InvariantCulture), ids.CarId.ToString(CultureInfo.InvariantCulture), drivetrainId,
                    powertrain.ToString(CultureInfo.InvariantCulture), F(massDiff), "0", level.ToString(CultureInfo.InvariantCulture), "0", F(price), "0" });
    }

    // ───────────── tyres ─────────────

    /// <summary>
    /// The tyre shop has one slot per level and every stock car uses the same compound in a slot
    /// (level 0 is the factory tyre of cars whose tyre isn't one of these). Level 4 is never used by a stock car.
    /// </summary>
    public static readonly (int Level, string Compound, string Label, string Model, int Price)[] CompoundSlots =
    {
        (1, "5", "Street", "a", 2000),
        (2, "6", "Sport", "a", 5000),
        (3, "7", "Race", "b", 10000),
        (4, "8", "Racing slick", "b", 12000),
        (5, "9", "Rally / off-road", "rally", 10000),
    };

    public static List<Donor> TireCompounds(ICarDb db, CarIds ids)
    {
        var used = UsedLevels(db, "List_UpgradeTireCompound", "Ordinal", ids.CarId);
        int stock = (int)(Scalar(db, $"SELECT Level FROM List_UpgradeTireCompound WHERE Ordinal = {ids.CarId} AND IsStock = 1;") ?? 0);
        var grip = db.Query("SELECT TireCompoundID, TorqueFreeLatFrictionScale FROM List_TireCompound;", out _)?.Rows.ToDictionary(r => r[0] ?? "", r => Num(r[1])) ?? new();
        var list = CompoundSlots.Where(s => !used.Contains(s.Level)).Select(s => new Donor(
            s.Level.ToString(CultureInfo.InvariantCulture), $"{s.Label} tyres",
            s.Level == 4 ? $"shop slot 4 · grip ×{F(grip.GetValueOrDefault(s.Compound))} · experimental: no stock car uses this slot, the shop may not show it"
                         : $"shop slot {s.Level} · grip ×{F(grip.GetValueOrDefault(s.Compound))}{(s.Level < stock ? " · below this car's stock tyre" : "")}",
            (s.Level == 4 ? 100 : 0) + (s.Level < stock ? 50 : 0) + s.Level, false)).OrderBy(d => d.Score).ToList();
        if (list.Count > 0 && list[0].Score < 100) list[0] = list[0] with { Recommended = true };
        return list;
    }

    public static int CompoundSlotPrice(string level) => CompoundSlots.FirstOrDefault(s => s.Level.ToString(CultureInfo.InvariantCulture) == level).Price;

    public static string BuildTireCompound(ICarDb db, CarIds ids, string level, double price)
    {
        var slot = CompoundSlots.First(s => s.Level.ToString(CultureInfo.InvariantCulture) == level);
        var src = db.Query($"SELECT * FROM List_UpgradeTireCompound WHERE Ordinal = {ids.CarId} ORDER BY ABS(Level - {slot.Level}), IsStock DESC LIMIT 1;", out var err)
                  ?? throw new InvalidOperationException(err);
        if (src.Rows.Count == 0) throw new InvalidOperationException("This car has no tyre data to copy from.");
        return CloneRows(db, "List_UpgradeTireCompound", "Ordinal", ids.CarId, ids.CarId * 1000, src, v =>
        {
            bool openWheel = (v["TireModelName"] ?? "").StartsWith("OW_", StringComparison.OrdinalIgnoreCase);
            v["Level"] = level;
            v["TireCompoundID"] = slot.Compound;
            v["Price"] = F(price);
            v["TireModelName"] = slot.Model == "rally" ? (openWheel ? "rallyow" : "rally") : (openWheel ? "OW_" : "") + slot.Model;
            return v;
        });
    }

    public static (double Front, double Rear) StockTireWidths(ICarDb db, CarIds ids)
    {
        var r = db.Query($"SELECT FrontTireWidthMM, RearTireWidthMM FROM Data_Car WHERE Id = {ids.CarId};", out _)?.Rows.FirstOrDefault();
        return (Num(r?[0]), Num(r?[1]));
    }

    public static string BuildTireWidth(ICarDb db, CarIds ids, double? front, double? rear, double price)
    {
        if (ids.BodyId is not { } body) throw new InvalidOperationException("This car has no body data.");
        var sb = new StringBuilder();
        foreach (var (table, column, width) in new[] { ("List_UpgradeCarBodyTireWidthFront", "FrontTireWidth", front), ("List_UpgradeCarBodyTireWidthRear", "RearTireWidth", rear) })
        {
            if (width is not { } w) continue;
            var src = db.Query($"SELECT * FROM {Q(table)} WHERE CarBodyId = {body} ORDER BY Level DESC LIMIT 1;", out _);
            if (src is not { Rows.Count: > 0 }) continue;
            // next slot above the widest option; if the top slot is taken, fill the highest free gap
            int max = MaxLevel(db, table, "CarBodyId", body);
            var free = FreeSlots(db, table, "CarBodyId", body);
            int level = free.Contains(max + 1) ? max + 1 : free.Where(l => l > 0).DefaultIfEmpty(-1).Max();
            if (level < 0) throw new InvalidOperationException($"All {(column.StartsWith("Front") ? "front" : "rear")} tyre-width shop slots are taken. Change an existing width in Tyres & grip instead.");
            sb.Append(CloneRows(db, table, "CarBodyId", body, body, src, v =>
            {
                v[column] = F(w);
                v["Price"] = F(price);
                v["Level"] = level.ToString(CultureInfo.InvariantCulture);
                return v;
            }));
        }
        return sb.ToString();
    }

    // ───────────── spacers ─────────────
    // The wheels sit where the body's outer track width says (Data_CarBody.ModelFront/RearTrackOuter, read when the car
    // is built). CarTrackOffsets looks like the right table but the game loads it and never uses it.
    // Which body a car uses comes from its installed List_UpgradeCarBody row, so a second body row pointing at a wider
    // copy of the body is a spacer part that can be bought in the shop. Catch: a part's mesh is found by its row id in the
    // car's .carbin, so body parts with several meshes (the front bumper) have no mesh on the copy and are not drawn.

    /// <summary>Tables keyed by CarBodyId: a body copy needs its own rows, the game drops parts of another body.</summary>
    public static readonly string[] BodyTables =
    {
        "List_UpgradeCarBodyTireWidthFront", "List_UpgradeCarBodyTireWidthRear", "List_UpgradeCarBodyWeight", "List_UpgradeCarBodyChassisStiffness",
        "List_UpgradeCarBodyFrontBumper", "List_UpgradeCarBodyRearBumper", "List_UpgradeCarBodyHood", "List_UpgradeCarBodySideSkirt",
    };

    public static (double Front, double Rear) BodyTrack(ICarDb db, long bodyId)
    {
        var r = db.Query($"SELECT ModelFrontTrackOuter, ModelRearTrackOuter FROM Data_CarBody WHERE Id = {bodyId};", out _)?.Rows.FirstOrDefault();
        return (Num(r?[0]), Num(r?[1]));
    }

    /// <summary>The body of the shop spacer upgrade this tool added to the car, if any.</summary>
    public static (long RowId, long BodyId, double Price)? ShopSpacer(ICarDb db, CarIds ids)
    {
        var r = db.Query($"SELECT Id, CarBodyID, Price FROM List_UpgradeCarBody WHERE Ordinal = {ids.CarId} AND IsStock = 0 ORDER BY Level LIMIT 1;", out _)?.Rows.FirstOrDefault();
        return r == null ? null : ((long)Num(r[0]), (long)Num(r[1]), Num(r[2]));
    }

    /// <summary>Per-side spacer of a body compared to the car's stock body, in mm.</summary>
    public static (double Front, double Rear) SpacerMm(ICarDb db, ICarDb stock, CarIds ids, long bodyId)
    {
        var s = BodyTrack(stock, ids.BodyId ?? 0);
        var c = BodyTrack(db, bodyId);
        return (Math.Round((c.Front - s.Front) * 500, 1), Math.Round((c.Rear - s.Rear) * 500, 1));
    }

    private static string TrackSql(long bodyId, (double Front, double Rear) stockTrack, double frontMm, double rearMm) =>
        CarModel.UpdateSql("Data_CarBody", "Id", bodyId.ToString(CultureInfo.InvariantCulture), new[]
        {
            ("ModelFrontTrackOuter", (string?)F4(stockTrack.Front + 2 * frontMm / 1000)),
            ("ModelRearTrackOuter", (string?)F4(stockTrack.Rear + 2 * rearMm / 1000)),
        });

    private static string F4(double v) => v.ToString("0.####", CultureInfo.InvariantCulture);

    /// <summary>Always-fitted spacers: widens the car's own body. Keeps every body part, not a shop item.</summary>
    public static string BuildFixedSpacers(ICarDb stock, CarIds ids, double frontMm, double rearMm)
    {
        if (ids.BodyId is not { } body) throw new InvalidOperationException("This car has no body data.");
        return TrackSql(body, BodyTrack(stock, body), frontMm, rearMm);
    }

    /// <summary>Shop spacers: a level-1 body upgrade that switches to a wider copy of the body (created once, then updated).</summary>
    public static string BuildShopSpacers(ICarDb db, ICarDb stock, CarIds ids, double frontMm, double rearMm, double price)
    {
        if (ids.BodyId is not { } body) throw new InvalidOperationException("This car has no body data.");
        var stockTrack = BodyTrack(stock, body);
        if (ShopSpacer(db, ids) is { } existing)
            return TrackSql(existing.BodyId, stockTrack, frontMm, rearMm) + "\n" +
                   CarModel.UpdateSql("List_UpgradeCarBody", "Id", existing.RowId.ToString(CultureInfo.InvariantCulture), new[] { ("Price", (string?)F(price)) });

        long copy = body + 500;
        while (Scalar(db, $"SELECT COUNT(*) FROM Data_CarBody WHERE Id = {copy};") is > 0) copy++;
        var sb = new StringBuilder();

        var src = db.Query($"SELECT * FROM Data_CarBody WHERE Id = {body};", out var err) ?? throw new InvalidOperationException(err);
        if (src.Rows.Count == 0) throw new InvalidOperationException("This car has no body data.");
        var bodyRow = src.Rows[0].ToArray();
        bodyRow[src.Columns.FindIndex(c => c.Equals("Id", StringComparison.OrdinalIgnoreCase))] = copy.ToString(CultureInfo.InvariantCulture);
        bodyRow[src.Columns.IndexOf("ModelFrontTrackOuter")] = F4(stockTrack.Front + 2 * frontMm / 1000);
        bodyRow[src.Columns.IndexOf("ModelRearTrackOuter")] = F4(stockTrack.Rear + 2 * rearMm / 1000);
        sb.AppendLine(CarModel.InsertSql("Data_CarBody", src.Columns, bodyRow));

        foreach (var table in BodyTables)
        {
            var rows = db.Query($"SELECT * FROM {Q(table)} WHERE CarBodyId = {body} ORDER BY Id;", out _);
            if (rows is not { Rows.Count: > 0 }) continue;
            int idIdx = rows.Columns.FindIndex(c => c.Equals("Id", StringComparison.OrdinalIgnoreCase));
            int bodyIdx = rows.Columns.FindIndex(c => c.Equals("CarBodyId", StringComparison.OrdinalIgnoreCase));
            var taken = new HashSet<long>();
            foreach (var row in rows.Rows)
            {
                var v = row.ToArray();
                // same offset under the copy (body 2177000 row 2177001 -> 2177501), stepping past taken ids
                long id = (long)Num(row[idIdx]) - body + copy;
                while (taken.Contains(id) || Scalar(db, $"SELECT COUNT(*) FROM {Q(table)} WHERE Id = {id};") is > 0)
                    if (++id >= body + 1000) throw new InvalidOperationException("No free id left for the spacer body.");
                taken.Add(id);
                v[idIdx] = id.ToString(CultureInfo.InvariantCulture);
                v[bodyIdx] = copy.ToString(CultureInfo.InvariantCulture);
                sb.AppendLine(CarModel.InsertSql(table, rows.Columns, v));
            }
        }

        var up = db.Query($"SELECT * FROM List_UpgradeCarBody WHERE Ordinal = {ids.CarId} ORDER BY IsStock DESC LIMIT 1;", out _);
        if (up is not { Rows.Count: > 0 }) throw new InvalidOperationException("This car has no body upgrade data.");
        var u = up.Columns.Select((c, i) => (c, up.Rows[0][i])).ToDictionary(x => x.c, x => x.Item2, StringComparer.OrdinalIgnoreCase);
        u["Id"] = NextId(db, "List_UpgradeCarBody", ids.CarId * 1000, new HashSet<long>()).ToString(CultureInfo.InvariantCulture);
        u["Level"] = (MaxLevel(db, "List_UpgradeCarBody", "Ordinal", ids.CarId) + 1).ToString(CultureInfo.InvariantCulture);
        u["CarBodyID"] = copy.ToString(CultureInfo.InvariantCulture);
        u["IsStock"] = "0";
        u["Price"] = F(price);
        u["MassDiff"] = "1.2";
        u["RequiresGraphics"] = "1";
        sb.AppendLine(CarModel.InsertSql("List_UpgradeCarBody", up.Columns, up.Columns.Select(c => u[c])));
        return sb.ToString();
    }

    /// <summary>Extra statements needed when removing an added row (a shop spacer takes its body copy with it).</summary>
    public static string RemovalExtras(ICarDb db, string table, string key)
    {
        if (table != "List_UpgradeCarBody") return "";
        var body = Scalar(db, $"SELECT CarBodyID FROM List_UpgradeCarBody WHERE Id = {key} AND IsStock = 0;");
        if (body is not { } b) return "";
        var sb = new StringBuilder($"DELETE FROM Data_CarBody WHERE Id = {b};\n");
        foreach (var t in BodyTables) sb.AppendLine($"DELETE FROM {Q(t)} WHERE CarBodyId = {b};");
        return sb.ToString();
    }

    // ───────────── extra level of an existing part ─────────────

    public static (string KeyColumn, long Key, long IdBase)? KeyFor(string table, CarIds ids)
    {
        if (table.StartsWith("List_UpgradeEngine", StringComparison.Ordinal) && table != "List_UpgradeEngine")
            return ids.EngineId is { } e ? ("EngineID", e, e * 1000) : null;
        if (table.StartsWith("List_UpgradeDrivetrain", StringComparison.Ordinal) && table != "List_UpgradeDrivetrain")
            return ids.DrivetrainId is { } d ? ("DrivetrainID", d, d * 1000) : null;
        if (table.StartsWith("List_UpgradeCarBody", StringComparison.Ordinal) && table != "List_UpgradeCarBody")
            return ids.BodyId is { } b ? ("CarBodyId", b, b) : null;
        return ("Ordinal", ids.CarId, ids.CarId * 1000);
    }

    public sealed record LevelSlot(string Table, int Level, int? StockLevel, int[] Used);

    /// <summary>Every free shop slot of the car's slotted parts that it already has at least one level of.</summary>
    public static List<LevelSlot> LevelSlots(ICarDb db, CarIds ids, IEnumerable<string> tables)
    {
        var list = new List<LevelSlot>();
        foreach (var t in tables)
        {
            if (SlotRange(t) is not { } s || KeyFor(t, ids) is not { } k) continue;
            var r = db.Query($"SELECT Level, IsStock FROM {Q(t)} WHERE {Q(k.KeyColumn)} = {k.Key};", out _);
            if (r is not { Rows.Count: > 0 }) continue;
            var used = r.Rows.Select(x => (int)Num(x[0])).Distinct().OrderBy(x => x).ToArray();
            int? stock = r.Rows.Where(x => x[1] == "1").Select(x => (int?)(int)Num(x[0])).FirstOrDefault();
            // level 0 is only ever the factory part in the stock data, so it is never offered as an upgrade
            var free = Enumerable.Range(Math.Max(1, s.Min), s.Max - Math.Max(1, s.Min) + 1).Where(l => !used.Contains(l)).ToList();
            if (!free.Any(l => l > (stock ?? -1))) list.Add(new LevelSlot(t, -1, stock, used));
            list.AddRange(free.Select(l => new LevelSlot(t, l, stock, used)));
        }
        // stronger-than-stock slots first; the rest would be cheaper downgrades
        return list.OrderBy(s => s.Level >= 0 && s.Level > (s.StockLevel ?? -1) ? 0 : 1).ToList();
    }

    /// <summary>Physics rows that belong to a level (their own Id per level: car × 1000 + level, +100 for the rear).</summary>
    private static readonly Dictionary<string, (string Column, string PhysicsTable, string PhysicsKey, int Offset)[]> LevelPhysics = new(StringComparer.Ordinal)
    {
        ["List_UpgradeSpringDamper"] = new[] { ("FrontSpringDamperPhysicsID", "List_SpringDamperPhysics", "SpringDamperPhysicsID", 0), ("RearSpringDamperPhysicsID", "List_SpringDamperPhysics", "SpringDamperPhysicsID", 100) },
        ["List_UpgradeAntiSwayFront"] = new[] { ("AntiSwayPhysicsID", "List_AntiSwayPhysics", "AntiSwayPhysicsID", 0) },
        ["List_UpgradeAntiSwayRear"] = new[] { ("AntiSwayPhysicsID", "List_AntiSwayPhysics", "AntiSwayPhysicsID", 100) },
        ["List_UpgradeRearWing"] = new[] { ("AeroPhysicsID", "List_AeroPhysics", "AeroPhysicsID", 850) },
        ["List_UpgradeCarBodyFrontBumper"] = new[] { ("AeroPhysicsID", "List_AeroPhysics", "AeroPhysicsID", 800) },
    };

    /// <summary>Fills a free shop slot of a part with a copy of the car's nearest level (and its own copy of that level's physics).</summary>
    public static string BuildExtraLevel(ICarDb db, CarIds ids, string table, int level)
    {
        var key = KeyFor(table, ids) ?? throw new InvalidOperationException("This part does not apply to this car.");
        if (!InShop(table, level) || level < 1) throw new InvalidOperationException($"The upgrade shop has no level {level} for this part.");
        if (UsedLevels(db, table, key.KeyColumn, key.Key).Contains(level)) throw new InvalidOperationException($"Level {level} of this part already exists.");
        var src = db.Query($"SELECT * FROM {Q(table)} WHERE {Q(key.KeyColumn)} = {key.Key} ORDER BY ABS(Level - {level}), Level DESC LIMIT 1;", out var err)
                  ?? throw new InvalidOperationException(err);
        if (src.Rows.Count == 0) throw new InvalidOperationException("Nothing to copy: this car has no level of that part yet.");
        int srcLevel = (int)Num(src.Rows[0][src.Columns.IndexOf("Level")]);

        var sb = new StringBuilder();
        var physicsIds = new Dictionary<string, string>();
        foreach (var (column, physTable, physKey, offset) in LevelPhysics.GetValueOrDefault(table) ?? Array.Empty<(string, string, string, int)>())
        {
            var oldId = src.Rows[0][src.Columns.IndexOf(column)];
            var phys = db.Query($"SELECT * FROM {Q(physTable)} WHERE {Q(physKey)} = {oldId};", out _);
            if (phys is not { Rows.Count: 1 }) continue;
            long newId = ids.CarId * 1000 + offset + level;
            while (Scalar(db, $"SELECT COUNT(*) FROM {Q(physTable)} WHERE {Q(physKey)} = {newId};") is > 0)
                if (++newId >= ids.CarId * 1000 + 1000) throw new InvalidOperationException("No free physics id left for this car.");
            var values = phys.Rows[0].ToArray();
            values[phys.Columns.IndexOf(physKey)] = newId.ToString(CultureInfo.InvariantCulture);
            sb.AppendLine(CarModel.InsertSql(physTable, phys.Columns, values));
            physicsIds[column] = newId.ToString(CultureInfo.InvariantCulture);
        }

        int priceIdx = src.Columns.IndexOf("Price");
        sb.Append(CloneRows(db, table, key.KeyColumn, key.Key, key.IdBase, src, v =>
        {
            v["Level"] = level.ToString(CultureInfo.InvariantCulture);
            if (priceIdx >= 0) v["Price"] = F(Math.Max(500, Math.Round(Num(v["Price"]) * (level > srcLevel ? 1.5 : 0.6) / 50) * 50));
            if (level == 4 && (table.StartsWith("List_UpgradeCarBody", StringComparison.Ordinal) || table == "List_UpgradeRearWing"))
            {
                v["RequiresGraphics"] = "0";
                v["IsStock"] = "0";
                if (v.ContainsKey("MassDiff")) v["MassDiff"] = "-2.0";
                v["Price"] = "100";
            }
            foreach (var (c, id) in physicsIds) v[c] = id;
            return v;
        }));
        return sb.ToString();
    }

    // ───────────── body part removal & quad turbo catalog ─────────────

    public static string EnsureQuadTurboCatalog(ICarDb db)
    {
        var sb = new StringBuilder();
        if (Scalar(db, "SELECT COUNT(*) FROM UpgradeTypes WHERE PartEnum = 26;") == 0)
        {
            sb.AppendLine("INSERT INTO UpgradeTypes (id, PartEnum, AreaId, IsException, DisplayOrder, EverymanUpgradeDisplayOrder, Name, Description, IconPath, ImagePath) " +
                          "VALUES (52, 26, 1, 0, 10, -1, '_&4038040853', '_&4038034807', " +
                          "'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_Icon.swatchbin', " +
                          "'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_LG_Icon.swatchbin');");
        }
        if (Scalar(db, "SELECT COUNT(*) FROM Upgrades WHERE TypeId = '52' AND Level = 0;") == 0)
        {
            sb.AppendLine("INSERT INTO Upgrades (id, TypeId, IsException, Name, Level, Description, IconPath, ImagePath) VALUES " +
                          "(280, '52', 0, '_&1888595974', 0, '_&1888559138', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\stock_Icon.swatchbin', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\stock_LG_Icon.swatchbin');");
        }
        if (Scalar(db, "SELECT COUNT(*) FROM Upgrades WHERE TypeId = '52' AND Level = 1;") == 0)
        {
            sb.AppendLine("INSERT INTO Upgrades (id, TypeId, IsException, Name, Level, Description, IconPath, ImagePath) VALUES " +
                          "(281, '52', 0, '_&1888595975', 1, '_&1888559266', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_1.swatchbin', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_LG_1.swatchbin');");
        }
        if (Scalar(db, "SELECT COUNT(*) FROM Upgrades WHERE TypeId = '52' AND Level = 2;") == 0)
        {
            sb.AppendLine("INSERT INTO Upgrades (id, TypeId, IsException, Name, Level, Description, IconPath, ImagePath) VALUES " +
                          "(282, '52', 0, '_&1888595976', 2, '_&1888560930', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_2.swatchbin', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_LG_2.swatchbin');");
        }
        if (Scalar(db, "SELECT COUNT(*) FROM Upgrades WHERE TypeId = '52' AND Level = 3;") == 0)
        {
            sb.AppendLine("INSERT INTO Upgrades (id, TypeId, IsException, Name, Level, Description, IconPath, ImagePath) VALUES " +
                          "(283, '52', 0, '_&1888595977', 3, '_&1888561058', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_3.swatchbin', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Engine_Power\\turbo_twin_LG_3.swatchbin');");
        }
        return sb.ToString();
    }

    public static string EnsureHoodRemovalCatalog(ICarDb db)
    {
        var sb = new StringBuilder();
        if (Scalar(db, "SELECT COUNT(*) FROM Upgrades WHERE TypeId = '28' AND Level = 4;") == 0)
        {
            sb.AppendLine("INSERT INTO Upgrades (id, TypeId, IsException, Name, Level, Description, IconPath, ImagePath) VALUES " +
                          "(278, '28', 0, '_&1888595972', 4, '_&1888595973', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Aero_Appearance\\hood_Icon.swatchbin', 'GAME:\\Media\\UI\\Textures\\Data_Bound\\Upgrade_Parts\\Aero_Appearance\\hood_LG_Icon.swatchbin');");
        }
        return sb.ToString();
    }

    public static string BuildBodyPartRemoval(ICarDb db, CarIds ids, string partKey, double price = 100, double massDiff = -2.0)
    {
        var sb = new StringBuilder();
        switch (partKey.ToLowerInvariant())
        {
            case "hood":
                sb.Append(EnsureHoodRemovalCatalog(db));
                if (ids.BodyId is { } bodyId)
                {
                    if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeCarBodyHood WHERE CarBodyId = {bodyId} AND Level = 4;") > 0)
                        throw new InvalidOperationException("Hood removal upgrade already exists on this car.");
                    long id = NextId(db, "List_UpgradeCarBodyHood", bodyId, new HashSet<long>());
                    sb.AppendLine(CarModel.InsertSql("List_UpgradeCarBodyHood",
                        new[] { "Id", "CarBodyID", "Level", "IsStock", "Sequence", "ManufacturerId", "PartsStringId", "MassDiff", "WeightDistDiff", "DragScale", "WindInstabilityScale", "Price", "RequiresGraphics" },
                        new[] { id.ToString(CultureInfo.InvariantCulture), bodyId.ToString(CultureInfo.InvariantCulture), "4", "0", "2", "0", "108", F(massDiff), "-0.001", "1.0", "1.0", ((int)price).ToString(CultureInfo.InvariantCulture), "0" }));
                }
                break;
            case "front_bumper":
                if (ids.BodyId is { } fbBodyId)
                {
                    if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeCarBodyFrontBumper WHERE CarBodyId = fbBodyId AND Level = 4;") > 0)
                        throw new InvalidOperationException("Front bumper removal upgrade already exists on this car.");
                    long id = NextId(db, "List_UpgradeCarBodyFrontBumper", fbBodyId, new HashSet<long>());
                    sb.AppendLine(CarModel.InsertSql("List_UpgradeCarBodyFrontBumper",
                        new[] { "Id", "CarBodyID", "Level", "IsStock", "Sequence", "ManufacturerId", "PartsStringId", "MassDiff", "DragScale", "WindInstabilityScale", "Price", "AeroPhysicsID", "RequiresGraphics" },
                        new[] { id.ToString(CultureInfo.InvariantCulture), fbBodyId.ToString(CultureInfo.InvariantCulture), "4", "0", "2", "255", "26", F(massDiff), "1.0", "1.0", ((int)price).ToString(CultureInfo.InvariantCulture), "20", "0" }));
                }
                break;
            case "rear_bumper":
                if (ids.BodyId is { } rbBodyId)
                {
                    if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeCarBodyRearBumper WHERE CarBodyId = rbBodyId AND Level = 4;") > 0)
                        throw new InvalidOperationException("Rear bumper removal upgrade already exists on this car.");
                    long id = NextId(db, "List_UpgradeCarBodyRearBumper", rbBodyId, new HashSet<long>());
                    sb.AppendLine(CarModel.InsertSql("List_UpgradeCarBodyRearBumper",
                        new[] { "Id", "CarBodyID", "Level", "IsStock", "Sequence", "ManufacturerId", "PartsStringId", "MassDiff", "DragScale", "WindInstabilityScale", "Price", "BodyAeroForwardDownforceFront", "BodyAeroForwardDownforceRear", "RequiresGraphics" },
                        new[] { id.ToString(CultureInfo.InvariantCulture), rbBodyId.ToString(CultureInfo.InvariantCulture), "4", "0", "2", "255", "53", F(massDiff), "1.0", "1.0", ((int)price).ToString(CultureInfo.InvariantCulture), "0.0", "0.0", "0" }));
                }
                break;
            case "rear_wing":
                if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeRearWing WHERE Ordinal = {ids.CarId} AND Level = 4;") > 0)
                    throw new InvalidOperationException("Rear wing removal upgrade already exists on this car.");
                long rwId = NextId(db, "List_UpgradeRearWing", ids.CarId * 1000, new HashSet<long>());
                sb.AppendLine(CarModel.InsertSql("List_UpgradeRearWing",
                    new[] { "Id", "Ordinal", "Level", "IsStock", "Sequence", "ManufacturerId", "PartsStringId", "MassDiff", "DragScale", "WindInstabilityScale", "Price", "AeroPhysicsID", "RequiresGraphics" },
                    new[] { rwId.ToString(CultureInfo.InvariantCulture), ids.CarId.ToString(CultureInfo.InvariantCulture), "4", "0", "2", "255", "80", F(massDiff), "0.97", "1.0", ((int)price).ToString(CultureInfo.InvariantCulture), "19", "0" }));
                break;
            case "side_skirts":
                if (ids.BodyId is { } ssBodyId)
                {
                    if (Scalar(db, $"SELECT COUNT(*) FROM List_UpgradeCarBodySideSkirt WHERE CarBodyId = ssBodyId AND Level = 4;") > 0)
                        throw new InvalidOperationException("Side skirts removal upgrade already exists on this car.");
                    long id = NextId(db, "List_UpgradeCarBodySideSkirt", ssBodyId, new HashSet<long>());
                    sb.AppendLine(CarModel.InsertSql("List_UpgradeCarBodySideSkirt",
                        new[] { "Id", "CarBodyID", "Level", "IsStock", "Sequence", "ManufacturerId", "PartsStringId", "MassDiff", "DragScale", "WindInstabilityScale", "Price", "RequiresGraphics" },
                        new[] { id.ToString(CultureInfo.InvariantCulture), ssBodyId.ToString(CultureInfo.InvariantCulture), "4", "0", "2", "255", "82", F(massDiff), "1.0", "1.0", ((int)price).ToString(CultureInfo.InvariantCulture), "0" }));
                }
                break;
        }
        return sb.ToString();
    }

    public static string UnlockAeroTuningForCar(ICarDb db, CarIds ids)
    {
        var sb = new StringBuilder();
        var wingRows = db.Query($"SELECT Id, Level, AeroPhysicsID FROM List_UpgradeRearWing WHERE Ordinal = {ids.CarId};", out _)?.Rows ?? new();
        var frontRows = ids.BodyId is { } b
            ? db.Query($"SELECT Id, Level, AeroPhysicsID FROM List_UpgradeCarBodyFrontBumper WHERE CarBodyId = {b};", out _)?.Rows ?? new()
            : new();

        var taken = new HashSet<long>();
        void ProcessPart(string table, List<List<string?>> rows, bool isWing)
        {
            foreach (var r in rows)
            {
                if (r[0] == null || r[2] == null) continue;
                string rowId = r[0]!;
                int level = (int)Num(r[1]);
                string oldPhysId = r[2]!;
                var phys = db.Query($"SELECT * FROM List_AeroPhysics WHERE AeroPhysicsID = {oldPhysId};", out _);
                if (phys == null || phys.Rows.Count == 0) continue;
                var physRow = phys.Rows[0];
                int df0Idx = phys.Columns.IndexOf("Downforce0"), df1Idx = phys.Columns.IndexOf("Downforce1");
                double df0 = df0Idx >= 0 ? Num(physRow[df0Idx]) : 0;
                double df1 = df1Idx >= 0 ? Num(physRow[df1Idx]) : 0;

                long baseId = ids.CarId * 1000 + (isWing ? 850 : 800) + Math.Clamp(level, 0, 99);
                long newPhysId = baseId;
                while (taken.Contains(newPhysId) || Scalar(db, $"SELECT COUNT(*) FROM List_AeroPhysics WHERE AeroPhysicsID = {newPhysId};") > 0)
                    newPhysId++;
                taken.Add(newPhysId);

                var values = physRow.ToArray();
                values[phys.Columns.IndexOf("AeroPhysicsID")] = newPhysId.ToString(CultureInfo.InvariantCulture);
                if (isWing)
                {
                    double d = df0 > 0 ? df0 : 34.02;
                    double min = Math.Round(d * 0.7, 2);
                    double max = Math.Round(Math.Max(d * 1.5, d + 25.0), 2);
                    if (df0Idx >= 0) values[df0Idx] = min.ToString("0.####", CultureInfo.InvariantCulture);
                    if (df1Idx >= 0) values[df1Idx] = max.ToString("0.####", CultureInfo.InvariantCulture);
                    int dr0 = phys.Columns.IndexOf("Drag0"), dr1 = phys.Columns.IndexOf("Drag1");
                    if (dr0 >= 0 && Num(values[dr0]) == 0) values[dr0] = "20.0";
                    if (dr1 >= 0 && Num(values[dr1]) <= Num(values[dr0])) values[dr1] = "45.0";
                }
                else
                {
                    double d = df0 > 0 ? df0 : 22.68;
                    double min = Math.Round(d * 0.7, 2);
                    double max = Math.Round(Math.Max(d * 1.5, d + 15.0), 2);
                    if (df0Idx >= 0) values[df0Idx] = min.ToString("0.####", CultureInfo.InvariantCulture);
                    if (df1Idx >= 0) values[df1Idx] = max.ToString("0.####", CultureInfo.InvariantCulture);
                    int dr0 = phys.Columns.IndexOf("Drag0"), dr1 = phys.Columns.IndexOf("Drag1");
                    if (dr0 >= 0 && Num(values[dr0]) == 0) values[dr0] = "10.0";
                    if (dr1 >= 0 && Num(values[dr1]) <= Num(values[dr0])) values[dr1] = "20.0";
                }
                int defIdx = phys.Columns.IndexOf("DefaultTuneSlider");
                if (defIdx >= 0) values[defIdx] = "0.5";

                sb.AppendLine(CarModel.InsertSql("List_AeroPhysics", phys.Columns, values));
                sb.AppendLine($"UPDATE {Q(table)} SET AeroPhysicsID = {newPhysId} WHERE Id = {rowId};");
            }
        }

        ProcessPart("List_UpgradeRearWing", wingRows, isWing: true);
        ProcessPart("List_UpgradeCarBodyFrontBumper", frontRows, isWing: false);
        return sb.ToString();
    }

    public static string UnlockAeroTuningForAllCars(ICarDb db)
    {
        var sb = new StringBuilder();
        // Front bumper shared IDs: 1, 2, 3, 20
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce0 = 15.0, Downforce1 = 35.0, Drag0 = 5.0, Drag1 = 15.0, DefaultTuneSlider = 0.5 WHERE AeroPhysicsID IN (1, 2);");
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce0 = 18.0, Downforce1 = 40.0, Drag0 = 8.0, Drag1 = 18.0, DefaultTuneSlider = 0.5 WHERE AeroPhysicsID = 3;");
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce0 = 0.0, Downforce1 = 30.0, Drag0 = 0.0, Drag1 = 15.0, DefaultTuneSlider = 0.5 WHERE AeroPhysicsID = 20;");
        // Rear wing shared IDs: 5, 6, 7, 19
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce0 = 25.0, Downforce1 = 70.0, Drag0 = 15.0, Drag1 = 35.0, DefaultTuneSlider = 0.5 WHERE AeroPhysicsID IN (5, 6);");
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce0 = 30.0, Downforce1 = 80.0, Drag0 = 18.0, Drag1 = 40.0, DefaultTuneSlider = 0.5 WHERE AeroPhysicsID = 7;");
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce0 = 0.0, Downforce1 = 50.0, Drag0 = 0.0, Drag1 = 25.0, DefaultTuneSlider = 0.5 WHERE AeroPhysicsID = 19;");
        // Also unlock any car-specific rows where Downforce0 == Downforce1
        sb.AppendLine("UPDATE List_AeroPhysics SET Downforce1 = CASE WHEN Downforce0 > 0 THEN Downforce0 * 1.5 ELSE 40.0 END, Drag1 = CASE WHEN Drag1 <= Drag0 THEN Drag0 + 15.0 ELSE Drag1 END WHERE Downforce0 = Downforce1 AND AeroPhysicsID NOT IN (1,2,3,4,5,6,7,8,19,20);");
        return sb.ToString();
    }
}
