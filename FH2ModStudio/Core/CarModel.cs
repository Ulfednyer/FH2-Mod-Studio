using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace FH2ModStudio.Core;

public sealed record CarEntry(long Id, string Media, string Make, int Year, string ClassText)
{
    public string Subtitle => $"{Make} · {Year} · {ClassText}";
}

public sealed record CarIds(long CarId, string Media, long? EngineId, long? DrivetrainId, int EngineShare, int DrivetrainShare, long? BodyId);

public enum GroupKind { Single, MultiRow, MultiTable }

/// <summary>One card in a section: a table row (or a choice of rows / tables) whose columns become editable fields.</summary>
public sealed class GroupDef
{
    public string Title { get; init; } = "";
    public string? Note { get; init; }
    public GroupKind Kind { get; init; }
    public string[] Tables { get; init; } = Array.Empty<string>();
    public string KeyColumn { get; init; } = "Id";
    public Func<CarIds, string?> Where { get; init; } = _ => null;     // null = not applicable for this car
    public string[]? Fields { get; init; }                              // null = every numeric column not hidden
    public (string Table, string Column, string Side)[] RowLabelRefs { get; init; } = Array.Empty<(string, string, string)>();
    public Func<CarIds, string?>? SharedWarning { get; init; }
    /// <summary>Which add-upgrade flow this card's "+ Add" button opens (null = none).</summary>
    public UpgradeKind? AddKind { get; init; }
}

public sealed record SectionDef(string Id, string Title, string Description, GroupDef[] Groups);

public sealed record FieldMeta(string Label, string? Unit = null, string? Help = null);

public static class CarModel
{
    public static readonly string[] ClassNames = { "D", "C", "B", "A", "S1", "S2", "X" };

    public static readonly HashSet<string> HiddenColumns = new(StringComparer.OrdinalIgnoreCase)
    {
        "Id", "Ordinal", "EngineID", "DrivetrainID", "ManufacturerID", "Level", "IsStock", "RequiresGraphics",
        "DamageModDefID", "SuspensionDamageModDefID", "TiresDamageModDefID", "PartsStringId", "Sequence",
        "FrontSpringDamperPhysicsID", "RearSpringDamperPhysicsID", "AntiSwayPhysicsID", "AeroPhysicsID",
        "TorqueCurveFullThrottleID", "NumRPMEntriesArray", "SpringDamperPhysicsID", "CarId", "CarBodyID", "PowertrainId",
        "MakeID", "ModelId", "ContentId", "StockWheelID", "GaugeID", "AIPlayerID", "TireBrandID", "FamilyModelID",
        "FamilyBodyID", "FamilySpecialID", "RegionID", "CountryID", "CarTypeID", "WingMask",
    };

    private static readonly string[] EngineParts =
    {
        "List_UpgradeEngineTurboSingle", "List_UpgradeEngineTurboTwin", "List_UpgradeEngineTurboQuad", "List_UpgradeEngineCSC",
        "List_UpgradeEngineDSC", "List_UpgradeEngineCamshaft", "List_UpgradeEngineDisplacement", "List_UpgradeEngineFlywheel",
        "List_UpgradeEngineExhaust", "List_UpgradeEngineIntake", "List_UpgradeEngineIntercooler", "List_UpgradeEngineManifold",
        "List_UpgradeEngineFuelSystem", "List_UpgradeEngineIgnition", "List_UpgradeEngineOilCooling",
        "List_UpgradeEnginePistonsCompression", "List_UpgradeEngineValves", "List_UpgradeEngineRestrictorPlate",
    };

    private static string? ByCar(CarIds c) => $"Ordinal = {c.CarId}";
    private static string? ByBody(CarIds c) => c.BodyId is { } b ? $"CarBodyId = {b}" : null;
    private static string? ByEngine(CarIds c) => c.EngineId is { } e ? $"EngineID = {e}" : null;
    private static string? ByDrivetrain(CarIds c) => c.DrivetrainId is { } d ? $"DrivetrainID = {d}" : null;
    private static string? EngineShared(CarIds c) => c.EngineShare > 1 ? $"This engine is shared with {c.EngineShare - 1} other car(s) - changes affect them too." : null;
    private static string? DrivetrainShared(CarIds c) => c.DrivetrainShare > 1 ? $"This drivetrain is shared with {c.DrivetrainShare - 1} other car(s) - changes affect them too." : null;

    private static GroupDef CarFields(string title, string? note, params string[] fields) => new()
    {
        Title = title, Note = note, Kind = GroupKind.Single, Tables = new[] { "Data_Car" }, KeyColumn = "Id",
        Where = c => $"Id = {c.CarId}", Fields = fields,
    };

    public static readonly SectionDef[] Sections =
    {
        new("overview", "Overview & menu stats", "Values shown in menus and used for the car's class. They don't change how it drives.", new[]
        {
            CarFields("Class & price", null, "ClassID", "PerformanceIndex", "BaseCost", "BaseRarity"),
            CarFields("Menu ratings", "Shown on the car's stat bars.", "SpeedRating", "HandlingRating", "AccelerationRating", "LaunchRating", "BrakingRating"),
            CarFields("Published figures", null, "Time:0-60-sec", "Time:0-100-sec", "TopSpeed-mph", "QuarterMileTime-sec", "QuarterMileSpeed-mph"),
        }),
        new("engine", "Engine", "Power, boost and every engine part with its upgrade levels.", new[]
        {
            CarFields("Power", "The torque multiplier is the simplest way to make a car faster or slower.",
                "GameTorqueScale", "Displacement", "AspirationTypeId", "EngineConfigID", "CylinderID", "EnginePlacementID"),
            new GroupDef
            {
                Title = "Engine block", Kind = GroupKind.Single, Tables = new[] { "Data_Engine" }, KeyColumn = "EngineID", Where = ByEngine,
                Fields = new[] { "EngineMass-kg", "Compression", "StockBoost-bar", "MomentInertia", "GasTankSize", "TorqueSteerLeftSpeedScale", "TorqueSteerRightSpeedScale", "Carbureted", "Diesel", "Rotary" },
                SharedWarning = EngineShared,
            },
            new GroupDef
            {
                Title = "Engine parts & upgrades", Note = "Pick a part, then the upgrade level. 'Stock' is the factory part.",
                Kind = GroupKind.MultiTable, Tables = EngineParts, Where = ByEngine, SharedWarning = EngineShared,
                AddKind = UpgradeKind.ExtraLevel,
            },
            new GroupDef
            {
                Title = "Engine swaps", Note = "Engines this car can be converted to in the upgrade shop.",
                Kind = GroupKind.MultiRow, Tables = new[] { "List_UpgradeEngine" }, Where = ByCar,
                Fields = new[] { "EngineID", "Price", "MassDiff", "WeightDistDiff", "DragScale" }, AddKind = UpgradeKind.EngineSwap,
            },
        }),
        new("drivetrain", "Drivetrain", "Drive type, gearbox ratios, differential and clutch.", new[]
        {
            new GroupDef
            {
                Title = "Layout", Kind = GroupKind.Single, Tables = new[] { "Data_Drivetrain" }, KeyColumn = "DrivetrainID", Where = ByDrivetrain,
                Fields = new[] { "DrivetypeID", "ShiftSystemID", "EngineMountingDirection" }, SharedWarning = DrivetrainShared,
            },
            new GroupDef
            {
                Title = "Gearbox, differential & clutch", Note = "Gear ratio -1 means the gear doesn't exist. Gear 0 is reverse.",
                Kind = GroupKind.MultiTable, Where = ByDrivetrain, SharedWarning = DrivetrainShared,
                Tables = new[] { "List_UpgradeDrivetrainTransmission", "List_UpgradeDrivetrainDifferential", "List_UpgradeDrivetrainClutch", "List_UpgradeDrivetrainDriveline" },
                AddKind = UpgradeKind.ExtraLevel,
            },
            new GroupDef
            {
                Title = "Drivetrain conversions", Note = "Drive-type conversions (e.g. AWD) offered in the upgrade shop.",
                Kind = GroupKind.MultiRow, Tables = new[] { "List_UpgradeDrivetrain" }, Where = ByCar,
                Fields = new[] { "DrivetrainID", "PowertrainId", "Price", "MassDiff", "WeightDistDiff" }, AddKind = UpgradeKind.DrivetrainSwap,
            },
        }),
        new("weight", "Weight & balance", "How heavy the car is and where the weight sits.", new[]
        {
            CarFields("Weight", null, "CurbWeight", "WeightDistribution", "MaterialTypeID"),
            CarFields("Stock ride height", null, "FrontStockRideHeight", "RearStockRideHeight"),
            new GroupDef
            {
                Title = "Weight reduction & chassis upgrades", Kind = GroupKind.MultiTable, Where = ByBody, KeyColumn = "Id",
                Tables = new[] { "List_UpgradeCarBodyWeight", "List_UpgradeCarBodyChassisStiffness" }, AddKind = UpgradeKind.ExtraLevel,
            },
        }),
        new("suspension", "Suspension", "Springs, dampers, geometry and anti-roll bars for every upgrade level.", new[]
        {
            new GroupDef
            {
                Title = "Springs, dampers & geometry", Kind = GroupKind.MultiRow, Tables = new[] { "List_SpringDamperPhysics" },
                KeyColumn = "SpringDamperPhysicsID", Where = ByCar,
                RowLabelRefs = new[] { ("List_UpgradeSpringDamper", "FrontSpringDamperPhysicsID", "front"), ("List_UpgradeSpringDamper", "RearSpringDamperPhysicsID", "rear") },
            },
            new GroupDef
            {
                Title = "Anti-roll bars", Kind = GroupKind.MultiRow, Tables = new[] { "List_AntiSwayPhysics" },
                KeyColumn = "AntiSwayPhysicsID", Where = ByCar,
                RowLabelRefs = new[] { ("List_UpgradeAntiSwayFront", "AntiSwayPhysicsID", "front"), ("List_UpgradeAntiSwayRear", "AntiSwayPhysicsID", "rear") },
            },
            new GroupDef
            {
                Title = "Suspension upgrade parts", Kind = GroupKind.MultiTable, Where = ByCar,
                Tables = new[] { "List_UpgradeSpringDamper", "List_UpgradeAntiSwayFront", "List_UpgradeAntiSwayRear" },
                AddKind = UpgradeKind.ExtraLevel,
            },
        }),
        new("tires", "Tyres & grip", "Tyre sizes, grip multipliers and tyre / rim upgrades.", new[]
        {
            CarFields("Tyre sizes", null, "FrontTireWidthMM", "FrontTireAspect", "FrontWheelDiameterIN", "RearTireWidthMM", "RearTireAspect", "RearWheelDiameterIN"),
            CarFields("Grip multipliers", "Higher values give more grip on that axle. 'Clamp' is the upper limit.",
                "LatFrontScalarMax", "LatFrontScalarClamp", "LatRearScalarMax", "LatRearScalarClamp",
                "LongAccelFrontScalarMax", "LongAccelFrontScalarClamp", "LongAccelRearScalarMax", "LongAccelRearScalarClamp",
                "LongBrakeFrontScalarMax", "LongBrakeFrontScalarClamp", "LongBrakeRearScalarMax", "LongBrakeRearScalarClamp",
                "FixListingRearFricScale"),
            new GroupDef
            {
                Title = "Tyre compound & rim upgrades", Kind = GroupKind.MultiTable, Where = ByCar,
                Tables = new[] { "List_UpgradeTireCompound", "List_UpgradeRimSizeFront", "List_UpgradeRimSizeRear" },
                AddKind = UpgradeKind.TireCompound,
            },
            new GroupDef
            {
                Title = "Tyre width upgrades", Kind = GroupKind.MultiTable, Where = ByBody,
                Tables = new[] { "List_UpgradeCarBodyTireWidthFront", "List_UpgradeCarBodyTireWidthRear" }, AddKind = UpgradeKind.TireWidth,
            },
            new GroupDef
            {
                Title = "Wheel spacers - always fitted", Note = "Outer track width of the body. +0.010 m = 5 mm spacer per side. Keeps every body part.",
                Kind = GroupKind.Single, Tables = new[] { "Data_CarBody" }, KeyColumn = "Id", Where = c => c.BodyId is { } b ? $"Id = {b}" : null,
                Fields = new[] { "ModelFrontTrackOuter", "ModelRearTrackOuter" }, AddKind = UpgradeKind.Spacers,
            },
            new GroupDef
            {
                Title = "Wheel spacers - shop upgrade", Note = "A body upgrade the shop sells. While it's fitted the front bumper is not drawn.",
                Kind = GroupKind.MultiRow, Tables = new[] { "List_UpgradeCarBody" }, Where = ByCar,
                Fields = new[] { "Price", "MassDiff" }, AddKind = UpgradeKind.Spacers,
            },
        }),
        new("brakes", "Brakes", "Brake strength, balance and ABS for every upgrade level.", new[]
        {
            new GroupDef { Title = "Brakes", Kind = GroupKind.MultiRow, Tables = new[] { "List_UpgradeBrakes" }, Where = ByCar, AddKind = UpgradeKind.ExtraLevel },
        }),
        new("aero", "Aerodynamics", "Drag and downforce of the body and wing upgrades.", new[]
        {
            CarFields("Body aerodynamics", null, "GameDragScale", "BodyAeroLongitudinalDrag", "BodyAeroVerticalDrag", "BodyAeroLateralDragFront",
                "BodyAeroLateralDragRear", "BodyAeroForwardDownforceFront", "BodyAeroForwardDownforceRear", "BodyAeroAngleZeroDownforce", "BodyAeroWIForceScale"),
            new GroupDef
            {
                Title = "Wing & bumper upgrades", Kind = GroupKind.MultiTable, Where = ByCar,
                Tables = new[] { "List_UpgradeRearWing", "List_UpgradeCarBodyFrontBumper" },
                AddKind = UpgradeKind.ExtraLevel,
            },
        }),
        new("steering", "Steering & assists", "Steering lock and speed, and traction-control thresholds.", new[]
        {
            CarFields("Steering", null, "SteerMaxAngle", "SteerMaxAngleFiltered", "SteerMaxAngVelTurning", "SteerMaxAngVelStraighten",
                "SteerAngVelCountersteer", "SteerAngVelDynFindPeak", "SteerAccelTimeToMaxRate", "SteerSpeedSensitiveMaxGees",
                "SteerSpeedSensitiveMinMaxAngle", "SteerSpeedSensitiveSlowSpeed", "SteerSpeedSensitiveFastSpeed", "SteerSpeedSensitiveFastRateScale"),
            CarFields("Traction control", null, "AssistsTCSSlipDefTakeoff", "AssistsTCSSlipDefMoving"),
        }),
        new("camera", "Camera", "Camera position offsets for this car.", new[]
        {
            new GroupDef { Title = "Camera offsets", Kind = GroupKind.Single, Tables = new[] { "CameraOverrides" }, KeyColumn = "CarId", Where = c => $"CarId = {c.CarId}" },
        }),
        new("all", "All car data", "Every number stored for this car, for anything not covered above.", new[]
        {
            new GroupDef { Title = "Data_Car", Kind = GroupKind.Single, Tables = new[] { "Data_Car" }, KeyColumn = "Id", Where = c => $"Id = {c.CarId}" },
        }),
    };

    // ───────────── labels, units, help ─────────────

    public static readonly Dictionary<string, FieldMeta> Meta = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ClassID"] = new("Class"),
        ["PerformanceIndex"] = new("Performance index", "×1000", "0.696 is shown as A 696."),
        ["BaseCost"] = new("Price", "CR"),
        ["BaseRarity"] = new("Rarity"),
        ["Time:0-60-sec"] = new("0-60 mph", "s"),
        ["Time:0-100-sec"] = new("0-100 mph", "s"),
        ["TopSpeed-mph"] = new("Top speed", "mph"),
        ["QuarterMileTime-sec"] = new("Quarter mile", "s"),
        ["QuarterMileSpeed-mph"] = new("Quarter mile speed", "mph"),
        ["GameTorqueScale"] = new("Torque multiplier", "×", "Scales the engine's torque. 1.10 = 10% more power."),
        ["GameDragScale"] = new("Drag multiplier", "×", "Lower = higher top speed."),
        ["Displacement"] = new("Displacement", "cc"),
        ["AspirationTypeId"] = new("Aspiration"),
        ["EngineConfigID"] = new("Engine layout"),
        ["CylinderID"] = new("Cylinders"),
        ["EnginePlacementID"] = new("Engine position"),
        ["EngineMass-kg"] = new("Engine mass", "kg"),
        ["StockBoost-bar"] = new("Stock boost", "bar"),
        ["Compression"] = new("Compression ratio", ": 1"),
        ["MomentInertia"] = new("Rotating inertia", null, "Lower = revs rise and fall faster."),
        ["GasTankSize"] = new("Fuel tank size"),
        ["DrivetypeID"] = new("Drive type", null, "Also updates the car's listed drive type."),
        ["DriveTypeID"] = new("Drive type"),
        ["ShiftSystemID"] = new("Shift system"),
        ["CurbWeight"] = new("Curb weight", "game units", "Roughly hundreds of kg (9.4 ≈ 940 kg)."),
        ["WeightDistribution"] = new("Front weight share", "0-1", "0.41 means 41% of the weight is on the front axle."),
        ["MaterialTypeID"] = new("Body material"),
        ["FrontStockRideHeight"] = new("Front ride height", "m"),
        ["RearStockRideHeight"] = new("Rear ride height", "m"),
        ["FrontTireWidthMM"] = new("Front tyre width", "mm"),
        ["FrontTireAspect"] = new("Front tyre profile", "%"),
        ["FrontWheelDiameterIN"] = new("Front rim size", "in"),
        ["RearTireWidthMM"] = new("Rear tyre width", "mm"),
        ["RearTireAspect"] = new("Rear tyre profile", "%"),
        ["RearWheelDiameterIN"] = new("Rear rim size", "in"),
        ["FinalDriveRatio"] = new("Final drive ratio"),
        ["GearRatio0"] = new("Reverse gear"),
        ["GearShiftTime"] = new("Shift time", "s"),
        ["NumGears"] = new("Number of gears"),
        ["ClutchMaxTorque"] = new("Clutch torque capacity"),
        ["ClutchInTime"] = new("Clutch engage time", "s"),
        ["ClutchOutTime"] = new("Clutch release time", "s"),
        ["RearToqueSplit"] = new("Rear torque split", "0-1", "Share of torque sent to the rear axle (AWD)."),
        ["RedlineRPM"] = new("Redline", "rpm"),
        ["StallRPM"] = new("Stall speed", "rpm"),
        ["StartRPM"] = new("Idle / start speed", "rpm"),
        ["TorqueCurveMaxRPM"] = new("Torque curve end", "rpm"),
        ["TorqueScale"] = new("Torque multiplier", "×"),
        ["Disp"] = new("Displacement", "cc"),
        ["MaxScale"] = new("Boost: max torque scale", "×"),
        ["PowerMaxScale"] = new("Boost: rpm at max scale"),
        ["MinScale"] = new("Boost: min torque scale", "×"),
        ["PowerMinScale"] = new("Boost: rpm at min scale"),
        ["RobScale"] = new("Low-rpm torque loss", "×"),
        ["TorqueDropOffRPM0"] = new("Drop-off starts", "rpm"),
        ["TorqueDropOffRPM1"] = new("Drop-off ends", "rpm"),
        ["TorqueDropOffScale0"] = new("Torque at drop-off start", "×"),
        ["TorqueDropOffScale1"] = new("Torque at drop-off end", "×"),
        ["MassDiff"] = new("Weight change"),
        ["WeightDistDiff"] = new("Weight balance change"),
        ["Price"] = new("Upgrade price", "CR"),
        ["DragScale"] = new("Drag multiplier", "×"),
        ["DefSpringRate"] = new("Spring rate (default)"),
        ["DefRideHeight"] = new("Ride height (default)", "m"),
        ["MinRideHeight"] = new("Ride height (min)", "m"),
        ["MaxRideHeight"] = new("Ride height (max)", "m"),
        ["DefDampenBumpRate"] = new("Bump damping (default)"),
        ["DefDampenReboundRate"] = new("Rebound damping (default)"),
        ["StaticCamber"] = new("Camber", "°"),
        ["StaticToe"] = new("Toe", "°"),
        ["Caster"] = new("Caster", "°"),
        ["DefSwaybarStiffness"] = new("Anti-roll stiffness (default)"),
        ["MinSwaybarStiffness"] = new("Anti-roll stiffness (min)"),
        ["MaxSwaybarStiffness"] = new("Anti-roll stiffness (max)"),
        ["GameFrictionScaleBraking"] = new("Brake grip multiplier", "×"),
        ["BrakeTorqueSlider"] = new("Brake pressure (default)", "0-1"),
        ["BrakeBiasSlider"] = new("Brake balance (default)", "0-1", "Higher = more front braking."),
        ["FrontBrakeSizeMM"] = new("Front disc size", "mm"),
        ["RearBrakeSizeMM"] = new("Rear disc size", "mm"),
        ["FrontBrakeTypeID"] = new("Front brake type"),
        ["RearBrakeTypeID"] = new("Rear brake type"),
        ["TireCompoundID"] = new("Tyre compound"),
        ["SteerMaxAngle"] = new("Steering lock", "°"),
        ["SuspensionPhysicsTypeID"] = new("Suspension type"),
        ["EngineID"] = new("Engine", null, "Which engine this upgrade installs."),
        ["DrivetrainID"] = new("Drivetrain", null, "Which drivetrain this conversion installs."),
        ["PowertrainId"] = new("Layout shown in menus"),
        ["FrontTireWidth"] = new("Front tyre width", "mm"),
        ["RearTireWidth"] = new("Rear tyre width", "mm"),
        ["ModelFrontTrackOuter"] = new("Front track width (outer)", "m", "Distance between the outer edges of the front wheels. +0.010 = 5 mm spacer per side."),
        ["ModelRearTrackOuter"] = new("Rear track width (outer)", "m", "Distance between the outer edges of the rear wheels. +0.010 = 5 mm spacer per side."),
        ["Mass"] = new("Body mass", "kg"),
        ["InitialMass"] = new("Original body mass", "kg"),
        ["CMHeight"] = new("Centre of mass height", "m"),
    };

    public static string Humanize(string column)
    {
        var s = Regex.Replace(column, @"[:\-_]+", " ");
        s = Regex.Replace(s, @"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])|(?<=[A-Z])(?=[A-Z][a-z])", " ");
        s = Regex.Replace(s, @"\b(sec|mph|kg|bar|MM|IN)\b", m => m.Value.ToLowerInvariant() switch { "sec" => "(s)", "in" => "(in)", "mm" => "(mm)", var u => $"({u})" });
        s = s.Trim();
        return s.Length > 0 ? char.ToUpperInvariant(s[0]) + s[1..].ToLowerInvariant() : column;
    }

    public static FieldMeta MetaFor(string column)
    {
        if (Meta.TryGetValue(column, out var m)) return m;
        var gear = Regex.Match(column, @"^GearRatio(\d)$");
        if (gear.Success) return new FieldMeta($"Gear {gear.Groups[1].Value} ratio");
        return new FieldMeta(Humanize(column));
    }

    public static bool IsFlag(string column, string? stock) =>
        (stock is "0" or "1") && Regex.IsMatch(column, @"^(Is|Has|Use|No)[A-Z]|^(Carbureted|Diesel|Rotary|TireAeroHackShouldApply)$");

    public static string TableLabel(string table)
    {
        var s = Regex.Replace(table, @"^List_Upgrade(Engine|Drivetrain|CarBody)?", "");
        return s switch
        {
            "CSC" => "Supercharger (centrifugal)",
            "DSC" => "Supercharger (positive displacement)",
            "TurboSingle" => "Single turbo",
            "TurboTwin" => "Twin turbo",
            "TurboQuad" => "Quad turbo",
            "PistonsCompression" => "Pistons & compression",
            "SpringDamper" => "Springs & dampers",
            "AntiSwayFront" => "Front anti-roll bar",
            "AntiSwayRear" => "Rear anti-roll bar",
            "TireCompound" => "Tyre compound",
            "RimSizeFront" => "Front rims",
            "RimSizeRear" => "Rear rims",
            "RearWing" => "Rear wing",
            "FrontBumper" => "Front bumper",
            _ => Humanize(s),
        };
    }

    // ───────────── option lists (enum columns) ─────────────

    public static Dictionary<string, List<(string Value, string Label)>> LoadOptions(ICarDb stock)
    {
        var options = new Dictionary<string, List<(string, string)>>(StringComparer.OrdinalIgnoreCase);
        void Add(string sql, params string[] columns)
        {
            var r = stock.Query(sql, out _);
            if (r == null) return;
            var list = r.Rows.Where(x => x[0] != null).Select(x => (x[0]!, string.IsNullOrWhiteSpace(x[1]) ? x[0]! : x[1]!)).ToList();
            foreach (var c in columns) options[c] = list;
        }
        Add("SELECT ID, DriveType FROM List_DriveType ORDER BY ID;", "DrivetypeID", "DriveTypeID");
        Add("SELECT AspirationID, Aspiration FROM List_Aspiration ORDER BY AspirationID;", "AspirationTypeId", "AspirationID_Stock");
        Add("SELECT ConfigID, EngineConfig FROM List_EngineConfig ORDER BY ConfigID;", "EngineConfigID", "ConfigID");
        Add("SELECT ID, EnginePlacement FROM List_EnginePlacement ORDER BY ID;", "EnginePlacementID");
        Add("SELECT CylinderID, CASE WHEN Rotors > 0 THEN Rotors || ' rotors' ELSE Number || ' cylinders' END FROM List_Cylinders ORDER BY CylinderID;", "CylinderID");
        Add("SELECT BrakeTypeID, BrakeType FROM List_BrakeType ORDER BY BrakeTypeID;", "FrontBrakeTypeID", "RearBrakeTypeID");
        Add("SELECT MaterialTypeID, Material FROM List_MaterialType ORDER BY MaterialTypeID;", "MaterialTypeID");
        Add("SELECT TireCompoundID, DisplayName FROM List_TireCompound ORDER BY TireCompoundID;", "TireCompoundID");
        Add("SELECT SuspensionPhysicsTypeID, Name FROM List_SuspensionPhysicsType ORDER BY SuspensionPhysicsTypeID;", "SuspensionPhysicsTypeID");
        options["ClassID"] = ClassNames.Select((n, i) => (i.ToString(CultureInfo.InvariantCulture), n)).ToList();
        Add("SELECT e.EngineID, MIN(c.MediaName) || ' engine' FROM Data_Engine e JOIN List_UpgradeEngine u ON u.EngineID = e.EngineID " +
            "JOIN Data_Car c ON c.Id = u.Ordinal GROUP BY e.EngineID ORDER BY 2;", "EngineID");
        Add("SELECT d.DrivetrainID, t.DriveType || ' · ' || MIN(c.MediaName) FROM Data_Drivetrain d JOIN List_DriveType t ON t.ID = d.DrivetypeID " +
            "JOIN List_UpgradeDrivetrain u ON u.DrivetrainID = d.DrivetrainID JOIN Data_Car c ON c.Id = u.Ordinal GROUP BY d.DrivetrainID ORDER BY 2;", "DrivetrainID");
        Add("SELECT p.Id, t.DriveType || ' · ' || pl.EnginePlacement || ' engine' FROM Powertrains p JOIN List_DriveType t ON t.ID = p.DrivetrainId " +
            "JOIN List_EnginePlacement pl ON pl.ID = p.EnginePlacementId ORDER BY p.Id;", "PowertrainId");
        return options;
    }

    // ───────────── catalog & ids ─────────────

    public static List<CarEntry> LoadCatalog(ICarDb stock, string carsDir)
    {
        var media = Directory.Exists(carsDir)
            ? new HashSet<string>(Directory.GetFiles(carsDir, "*.zip").Select(Path.GetFileNameWithoutExtension)!, StringComparer.OrdinalIgnoreCase)
            : null;
        var r = stock.Query("SELECT c.Id, c.MediaName, c.Year, c.ClassID, c.PerformanceIndex, m.IconPathBase FROM Data_Car c " +
                            "LEFT JOIN List_CarMake m ON m.ID = c.MakeID ORDER BY c.MediaName;", out _);
        if (r == null) return new();
        var list = new List<CarEntry>();
        foreach (var row in r.Rows)
        {
            var name = row[1] ?? "";
            if (name.Length == 0 || (media != null && !media.Contains(name))) continue;
            int.TryParse(row[3], out var cls);
            double.TryParse(row[4], NumberStyles.Float, CultureInfo.InvariantCulture, out var pi);
            var make = Regex.Replace(row[5] ?? "", @"(?<=[a-z])(?=[A-Z])", " ");
            int.TryParse(row[2], out var year);
            var classText = $"{ClassNames[Math.Clamp(cls, 0, ClassNames.Length - 1)]} {Math.Round(pi * 1000)}";
            list.Add(new CarEntry(long.Parse(row[0]!, CultureInfo.InvariantCulture), name, make.Length > 0 ? make : "Unknown make", year, classText));
        }
        return list;
    }

    public static CarIds ResolveIds(ICarDb db, CarEntry car)
    {
        long? Scalar(string sql) => db.Query(sql, out _) is { Rows.Count: > 0 } r && long.TryParse(r.Rows[0][0], out var v) ? v : null;
        var engine = Scalar($"SELECT EngineID FROM List_UpgradeEngine WHERE Ordinal = {car.Id} AND IsStock = 1 LIMIT 1;")
                     ?? Scalar($"SELECT EngineID FROM List_UpgradeEngine WHERE Ordinal = {car.Id} ORDER BY Level LIMIT 1;");
        var drive = Scalar($"SELECT DrivetrainID FROM List_UpgradeDrivetrain WHERE Ordinal = {car.Id} AND IsStock = 1 LIMIT 1;")
                    ?? Scalar($"SELECT DrivetrainID FROM List_UpgradeDrivetrain WHERE Ordinal = {car.Id} ORDER BY Level LIMIT 1;");
        int engineShare = engine is { } e ? (int)(Scalar($"SELECT COUNT(DISTINCT Ordinal) FROM List_UpgradeEngine WHERE EngineID = {e};") ?? 1) : 0;
        int driveShare = drive is { } d ? (int)(Scalar($"SELECT COUNT(DISTINCT Ordinal) FROM List_UpgradeDrivetrain WHERE DrivetrainID = {d};") ?? 1) : 0;
        var body = Scalar($"SELECT CarBodyID FROM List_UpgradeCarBody WHERE Ordinal = {car.Id} AND IsStock = 1 LIMIT 1;")
                   ?? Scalar($"SELECT CarBodyID FROM List_UpgradeCarBody WHERE Ordinal = {car.Id} LIMIT 1;");
        return new CarIds(car.Id, car.Media, engine, drive, engineShare, driveShare, body);
    }

    // ───────────── comparing & saving ─────────────

    public static bool SameValue(string? a, string? b)
    {
        if (a == b) return true;
        if (a == null || b == null) return false;
        if (double.TryParse(a, NumberStyles.Float, CultureInfo.InvariantCulture, out var x) &&
            double.TryParse(b, NumberStyles.Float, CultureInfo.InvariantCulture, out var y))
            return Math.Abs(x - y) <= 1e-6 * Math.Max(1, Math.Max(Math.Abs(x), Math.Abs(y)));
        return false;
    }

    public static string UpdateSql(string table, string keyColumn, string keyValue, IEnumerable<(string Column, string? Value)> sets) =>
        $"UPDATE {DbHistory.QuoteIdent(table)} SET {string.Join(", ", sets.Select(s => $"{DbHistory.QuoteIdent(s.Column)} = {DbHistory.Literal(s.Value)}"))} " +
        $"WHERE {DbHistory.QuoteIdent(keyColumn)} = {DbHistory.Literal(keyValue)};";

    /// <summary>Every difference between the current data and stock for this car, as UPDATE statements.</summary>
    public static string DiffAgainstStock(ICarDb current, ICarDb stock, CarIds ids, bool towardsStock = false)
    {
        var sb = new StringBuilder();
        var seen = new HashSet<string>();

        void DiffTable(string table, string keyColumn, string where)
        {
            if (!seen.Add(table + "|" + where)) return;
            var cur = current.Query($"SELECT * FROM {DbHistory.QuoteIdent(table)} WHERE {where};", out _);
            var stk = stock.Query($"SELECT * FROM {DbHistory.QuoteIdent(table)} WHERE {where};", out _);
            if (cur == null || stk == null) return;
            int keyIdx = cur.Columns.FindIndex(c => c.Equals(keyColumn, StringComparison.OrdinalIgnoreCase));
            int sKeyIdx = stk.Columns.FindIndex(c => c.Equals(keyColumn, StringComparison.OrdinalIgnoreCase));
            if (keyIdx < 0 || sKeyIdx < 0) return;
            var stockRows = stk.Rows.Where(r => r[sKeyIdx] != null).GroupBy(r => r[sKeyIdx]!).ToDictionary(g => g.Key, g => g.First());
            foreach (var row in cur.Rows)
            {
                if (row[keyIdx] is not { } key) continue;
                if (!stockRows.TryGetValue(key, out var srow))
                {
                    // a row the user added (new upgrade level, swap, spacer body): keep it, or remove it when resetting
                    sb.AppendLine(towardsStock
                        ? $"DELETE FROM {DbHistory.QuoteIdent(table)} WHERE {DbHistory.QuoteIdent(keyColumn)} = {DbHistory.Literal(key)};"
                        : InsertSql(table, cur.Columns, row));
                    continue;
                }
                var sets = new List<(string, string?)>();
                for (int i = 0; i < cur.Columns.Count; i++)
                {
                    int si = stk.Columns.IndexOf(cur.Columns[i]);
                    if (si < 0 || i == keyIdx || SameValue(row[i], srow[si])) continue;
                    sets.Add((cur.Columns[i], towardsStock ? srow[si] : row[i]));
                }
                if (sets.Count > 0) sb.AppendLine(UpdateSql(table, keyColumn, key, sets));
            }
        }

        foreach (var group in Sections.SelectMany(s => s.Groups))
        {
            if (group.Where(ids) is not { } where) continue;
            foreach (var table in group.Tables) DiffTable(table, group.KeyColumn, where);
        }

        // extra bodies (shop spacer copies) and everything keyed to them
        var bodies = current.Query($"SELECT CarBodyID FROM List_UpgradeCarBody WHERE Ordinal = {ids.CarId} AND CarBodyID <> {ids.BodyId ?? -1};", out _);
        foreach (var b in bodies?.Rows.Select(r => r[0]).Where(v => v != null).Distinct() ?? Enumerable.Empty<string?>())
        {
            DiffTable("Data_CarBody", "Id", $"Id = {b}");
            foreach (var t in Upgrades.BodyTables) DiffTable(t, "Id", $"CarBodyId = {b}");
        }
        return sb.ToString();
    }

    public static string InsertSql(string table, IEnumerable<string> columns, IEnumerable<string?> values) =>
        $"INSERT OR REPLACE INTO {DbHistory.QuoteIdent(table)} ({string.Join(", ", columns.Select(DbHistory.QuoteIdent))}) " +
        $"VALUES ({string.Join(", ", values.Select(DbHistory.Literal))});";

    public static string ModName(string media) => "Car · " + media;

    /// <summary>Stores the car's complete difference from stock as one saved mod (removed when nothing differs).</summary>
    public static void UpsertCarMod(ModSettings settings, string media, string diffSql)
    {
        var name = ModName(media);
        var existing = settings.DbMods.FirstOrDefault(m => m.Name == name);
        if (string.IsNullOrWhiteSpace(diffSql))
        {
            if (existing != null) settings.DbMods.Remove(existing);
        }
        else if (existing != null)
        {
            existing.Sql = diffSql;
            existing.Enabled = true;
        }
        else
        {
            settings.DbMods.Add(new DbMod { Name = name, Sql = diffSql, Enabled = true });
        }
        settings.Save();
    }
}
