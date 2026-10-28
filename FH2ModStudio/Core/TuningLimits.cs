using System.Globalization;
using System.Text.RegularExpressions;

namespace FH2ModStudio.Core;

public sealed record TuneField(string Key, int Offset, string Label, string Group);

/// <summary>
/// The tuning menu's slider ranges: [CarTuning] in Mount\media\physics\PhysicsSettings.ini. App::Initialize creates the
/// physics settings object (pointer at 0x14365D6E8) and sub_14104E390 binds every key to a float of it
/// (TuneFinalDriveRatioMin = +608 ... TuneGasTankFillMax = +728). Offline: the ini (read at game start, original kept as
/// PhysicsSettings.ini.orig). Live: the floats in game memory.
/// </summary>
public static class TuningLimits
{
    public const long SettingsPointer = 0x14365D6E8;
    /// <summary>The game also copies the ranges (same order, settings +608 -> here) into a static block the physics reads:
    /// it stores a tune as a 0..1 slider position and applies min + (max - min) * position (camber: sub_1412E3D20 reads
    /// 0x14367B018/1C). The settings object only drives the tuning menu, so a live change must write both.</summary>
    public const long StaticBlock = 0x14367AFD0;
    private const int FirstOffset = 608;

    private static long StaticAddress(TuneField f) => StaticBlock + (f.Offset - FirstOffset);

    public static readonly TuneField[] Fields =
    {
        new("TuneFinalDriveRatioMin", 608, "Final drive ratio", "Gearing"), new("TuneFinalDriveRatioMax", 612, "Final drive ratio", "Gearing"),
        new("TuneGearRatioMin", 616, "Gear ratios", "Gearing"), new("TuneGearRatioMax", 620, "Gear ratios", "Gearing"),
        new("TuneCamberMin", 680, "Camber (°)", "Alignment"), new("TuneCamberMax", 684, "Camber (°)", "Alignment"),
        new("TuneToeMin", 688, "Toe (°)", "Alignment"), new("TuneToeMax", 692, "Toe (°)", "Alignment"),
        new("TuneCasterMin", 696, "Caster (°)", "Alignment"), new("TuneCasterMax", 700, "Caster (°)", "Alignment"),
        new("TuneTirePressureMin", 672, "Tyre pressure (psi)", "Tyres"), new("TuneTirePressureMax", 676, "Tyre pressure (psi)", "Tyres"),
        new("TuneBrakePressureMin", 704, "Brake pressure", "Brakes"), new("TuneBrakePressureMax", 708, "Brake pressure", "Brakes"),
        new("TuneHandbrakePressureMin", 624, "Handbrake pressure", "Brakes"), new("TuneHandbrakePressureMax", 628, "Handbrake pressure", "Brakes"),
        new("TuneABSReleasePointMin", 632, "ABS release point", "Brakes"), new("TuneABSReleasePointMax", 636, "ABS release point", "Brakes"),
        new("TuneABSDurationMin", 640, "ABS duration", "Brakes"), new("TuneABSDurationMax", 644, "ABS duration", "Brakes"),
        new("TuneDiffTorqueSplitMin", 648, "AWD torque split", "Differential"), new("TuneDiffTorqueSplitMax", 652, "AWD torque split", "Differential"),
        new("TuneLSDTorqueMin", 712, "LSD torque", "Differential"), new("TuneLSDTorqueMax", 716, "LSD torque", "Differential"),
        new("TuneLSDTorqueMaxDecel", 720, "LSD torque, decel max", "Differential"),
        new("TuneSTMScaleMin", 656, "Stability control (STM) scale", "Assists"), new("TuneSTMScaleMax", 660, "Stability control (STM) scale", "Assists"),
        new("TuneTCSSlipDefMin", 664, "Traction control slip", "Assists"), new("TuneTCSSlipDefMax", 668, "Traction control slip", "Assists"),
        new("TuneGasTankFillMin", 724, "Fuel tank fill", "Other"), new("TuneGasTankFillMax", 728, "Fuel tank fill", "Other"),
    };

    private static readonly Regex Line = new(@"^(?<k>CarTuning\\(?<n>\w+))(?<sp>\s+)(?<v>\S+)", RegexOptions.Compiled);

    public static string IniPath(ModSettings s) => Path.Combine(s.MediaDir, "physics", "PhysicsSettings.ini");
    public static string StockPath(ModSettings s) => IniPath(s) + ".orig";

    public static Dictionary<string, double> ReadFile(string path)
    {
        var values = new Dictionary<string, double>();
        if (!File.Exists(path)) return values;
        foreach (var l in File.ReadLines(path))
        {
            var m = Line.Match(l);
            if (m.Success && double.TryParse(m.Groups["v"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var v))
                values[m.Groups["n"].Value] = v;
        }
        return values;
    }

    /// <summary>The game's own values: PhysicsSettings.ini as shipped (the .orig copy once we changed it).</summary>
    public static Dictionary<string, double> ReadStock(ModSettings s) => ReadFile(File.Exists(StockPath(s)) ? StockPath(s) : IniPath(s));

    /// <summary>Writes the values into PhysicsSettings.ini, keeping every other line; the original is kept once as .orig.</summary>
    public static void WriteFile(ModSettings s, IReadOnlyDictionary<string, double> values)
    {
        var path = IniPath(s);
        if (!File.Exists(StockPath(s))) File.Copy(path, StockPath(s));
        var text = File.ReadAllText(path);
        bool finalNewline = text.EndsWith('\n');                 // the shipped file has none: keep it byte-identical
        var lines = text.Split("\r\n").SelectMany(l => l.Split('\n')).ToList();
        if (finalNewline) lines.RemoveAt(lines.Count - 1);
        var done = new HashSet<string>();
        for (int i = 0; i < lines.Count; i++)
        {
            var m = Line.Match(lines[i]);
            if (m.Success && values.TryGetValue(m.Groups["n"].Value, out var v))
            {
                lines[i] = m.Groups["k"].Value + m.Groups["sp"].Value + Fmt(v) + lines[i][m.Length..];
                done.Add(m.Groups["n"].Value);
            }
        }
        foreach (var (k, v) in values.Where(kv => !done.Contains(kv.Key)))
            lines.Add($"CarTuning\\{k} {Fmt(v)}");
        File.WriteAllText(path, string.Join("\r\n", lines) + (finalNewline ? "\r\n" : ""));
    }

    private static string Fmt(double v) => v.ToString("0.####", CultureInfo.InvariantCulture);

    /// <summary>The live settings object, after checking the values look like tuning ranges.</summary>
    public static long? LiveObject(GameProcess g)
    {
        if (g.ReadInt64(SettingsPointer) is not { } p || p < 0x10000) return null;
        var fdMin = g.ReadFloat(p + 608);
        var fdMax = g.ReadFloat(p + 612);
        var camMin = g.ReadFloat(p + 680);
        var camMax = g.ReadFloat(p + 684);
        var sMin = g.ReadFloat(StaticBlock);                   // static copy loaded too (App::vf00 reads the ini again)
        var sMax = g.ReadFloat(StaticBlock + 4);
        bool sane = fdMin is > 0 and < 100 && fdMax > fdMin && camMax > camMin && sMin is > 0 and < 100 && sMax > sMin;
        return sane ? p : null;
    }

    /// <summary>The ranges the physics applies (static block).</summary>
    public static Dictionary<string, double>? ReadLive(GameProcess g)
    {
        if (LiveObject(g) is null) return null;
        var values = new Dictionary<string, double>();
        foreach (var f in Fields)
            if (g.ReadFloat(StaticAddress(f)) is { } v) values[f.Key] = Math.Round(v, 4);
        return values;
    }

    /// <summary>Writes the tuning menu's ranges (settings object) and the ranges the physics applies (static block).</summary>
    /// <returns>Number of values written, or -1 when the settings object wasn't found.</returns>
    public static int WriteLive(GameProcess g, IReadOnlyDictionary<string, double> values)
    {
        if (LiveObject(g) is not { } p) return -1;
        int n = 0;
        foreach (var f in Fields)
        {
            if (!values.TryGetValue(f.Key, out var v)) continue;
            bool menu = g.WriteFloat(p + f.Offset, (float)v);
            bool physics = g.WriteFloat(StaticAddress(f), (float)v);
            if (menu && physics) n++;
        }
        return n;
    }
}
