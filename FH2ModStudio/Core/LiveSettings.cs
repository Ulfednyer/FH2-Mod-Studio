namespace FH2ModStudio.Core;

public enum FieldType { Float, Int }

public sealed record LiveField(string Name, string Label, string Owner, int Offset, FieldType Type, bool VisibleEffect);

/// <summary>
/// Reads/writes render settings directly in game memory. Objects are found by vftable and every address is
/// re-validated before use (objects get freed and reused while the game runs).
/// </summary>
public sealed class LiveSettings
{
    private const long TrackSettingsOffset = 0x8110;

    private static readonly Dictionary<string, long[]> Vftables = new()
    {
        ["track"] = new[] { 0x142EC30C0L, 0x142EC23D8L },     // TrackPresentation11 (+0x8110 = parsed tracksettings.xml)
        ["carlod"] = new[] { 0x142EB9BB0L },
        ["crowdscale"] = new[] { 0x142EBA160L },
        ["framerate"] = new[] { 0x142EB98D0L },
        ["shadowres"] = new[] { 0x142EBA5D8L },
        ["hidefshadows"] = new[] { 0x142EBA620L },
        ["windshieldres"] = new[] { 0x142EBA668L },
        ["envmapfreq"] = new[] { 0x142EBA2F8L },
        ["mirrorcars"] = new[] { 0x142EBA340L },
    };

    public static readonly LiveField[] Fields =
    {
        new("ShadowMapResolution", "Shadow map resolution", "shadowres", 8, FieldType.Int, true),
        new("WindshieldReflectionResolution", "Windshield reflection resolution", "windshieldres", 8, FieldType.Int, true),
        new("MaxHiDefShadows", "Cars with high-detail shadows", "hidefshadows", 8, FieldType.Int, true),
        new("EnvMapFrequencyScale", "Reflection update rate", "envmapfreq", 8, FieldType.Float, true),
        new("MaxCarsInMirror", "Cars drawn in mirrors", "mirrorcars", 8, FieldType.Int, true),
        new("FrameRate", "Motion blur reference FPS", "framerate", 8, FieldType.Int, true),
        new("CarLODNear", "Car detail distance: near", "carlod", 0x8, FieldType.Float, true),
        new("CarLODFar", "Car detail distance: far", "carlod", 0xC, FieldType.Float, true),
        new("CarLODVeryFar", "Car detail distance: very far", "carlod", 0x10, FieldType.Float, true),
        new("CarLODFarthest", "Car detail distance: farthest", "carlod", 0x14, FieldType.Float, true),
        new("CrowdSpriteDistScale", "Crowd sprite distance scale", "crowdscale", 0x8, FieldType.Float, true),
        new("InGameShadowEnd", "Track: shadow end distance", "track", 0x234, FieldType.Float, false),
        new("GrassFadeEndDistance", "Track: grass fade end", "track", 0x168, FieldType.Float, false),
        new("CrowdVisibleDistance", "Track: crowd visible distance", "track", 0x404, FieldType.Float, false),
        new("CubemapFarDistance", "Track: cubemap far distance", "track", 0x2D4, FieldType.Float, false),
    };

    // MotionBlurAmount globals in .data, read every frame by each camera's GetMotionBlurAmount (vtable slot 0x1C).
    public static readonly (string Camera, long Address, float Default)[] BlurGlobals =
    {
        ("Driver (cockpit)", 0x142E77558, 1.0f),
        ("Hood", 0x142E77504, 0.6f),
        ("Bumper", 0x142E774E4, 0.6f),
    };

    public const long AaSampleCountAddress = 0x1434B1DD8;

    private int _pid;
    private Dictionary<string, List<long>> _instances = new();

    public bool HasScan(GameProcess g) => _pid == g.Pid && _instances.Count > 0;

    private bool Valid(GameProcess g, string owner, long addr)
    {
        var vft = g.ReadInt64(addr - (owner == "track" ? TrackSettingsOffset : 0));
        return vft.HasValue && Vftables[owner].Contains(vft.Value);
    }

    public void Scan(GameProcess g, CancellationToken token = default)
    {
        var needles = Vftables.Values.SelectMany(v => v).ToArray();
        var found = g.ScanForPointers(needles, token);
        _instances = Vftables.ToDictionary(kv => kv.Key,
            kv => kv.Value.SelectMany(v => found[v]).Select(a => a + (kv.Key == "track" ? TrackSettingsOffset : 0)).OrderBy(a => a).ToList());
        _pid = g.Pid;
    }

    /// <returns>Active value (first valid instance = the current scenario's setting), or null.</returns>
    public double? Read(GameProcess g, LiveField f)
    {
        if (!_instances.TryGetValue(f.Owner, out var list)) return null;
        foreach (var a in list)
        {
            if (!Valid(g, f.Owner, a)) continue;
            return f.Type == FieldType.Float ? g.ReadFloat(a + f.Offset) : g.ReadInt32(a + f.Offset);
        }
        return null;
    }

    public int Write(GameProcess g, LiveField f, double value)
    {
        if (!_instances.TryGetValue(f.Owner, out var list)) return 0;
        int n = 0;
        foreach (var a in list.Where(a => Valid(g, f.Owner, a)))
        {
            bool ok = f.Type == FieldType.Float ? g.WriteFloat(a + f.Offset, (float)value) : g.WriteInt32(a + f.Offset, (int)Math.Round(value));
            if (ok) n++;
        }
        return n;
    }

    public static float? ReadBlur(GameProcess g, int index) => g.IsGameLoaded ? g.ReadFloat(BlurGlobals[index].Address) : null;

    public static bool WriteBlur(GameProcess g, int index, float value) => g.IsGameLoaded && g.WriteFloat(BlurGlobals[index].Address, value);

    public static int? ReadMsaa(GameProcess g) => g.IsGameLoaded ? g.ReadInt32(AaSampleCountAddress) : null;
}
