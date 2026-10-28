using System.Globalization;
using System.Text.RegularExpressions;

namespace FH2ModStudio.Core;

public sealed record PresetInfo(string Id, string Title, string Summary, string Cost, int Shadow, int Windshield);

/// <summary>
/// Rebuilds media\renderscenarios from pristine originals and scales track draw distances.
/// Values come from the game's own option tables (shadow / reflection sizes 64..4096; 8192 works but is unlisted).
/// </summary>
public static class RenderPatcher
{
    public static readonly PresetInfo[] Presets =
    {
        new("stock", "Stock", "Game's original quality", "Fastest", 0, 0),
        new("balanced", "Balanced", "2048 shadows · 1024 reflections", "Light", 2048, 1024),
        new("max", "Max", "4096 shadows · 4096 reflections", "Heavy", 4096, 4096),
        new("ultra", "Ultra", "8192 shadows · 2048 reflections", "Heavy · tested", 8192, 2048),
        new("extreme", "Extreme", "8192 shadows · 8192 reflections", "Very heavy (≈8 GB VRAM)", 8192, 8192),
    };

    public static readonly int[] ResolutionOptions = { 512, 720, 1024, 2048, 4096, 8192 };

    private static readonly (string Tag, string Attr)[] ScenarioDistanceFields =
    {
        ("CarLODTransDist", "near"), ("CarLODTransDist", "far"), ("CarLODTransDist", "veryfar"),
        ("CarLODTransDist", "farthest"), ("CrowdSpriteDistScale", "value"),
    };

    private static readonly (string Tag, string Attr)[] TrackDistanceFields =
    {
        ("ShadowEnds", "InGameShadowEnd"), ("ShadowEnds", "TrackSegCamShadowEnd"),
        ("GrassLODDist", "value"), ("GrassFadeStartDistance", "value"), ("GrassFadeEndDistance", "value"),
        ("CollidableDropDistance", "value"), ("Cubemap", "FarDistance"),
        ("Crowds", "SpriteDistance"), ("Crowds", "VisibleDistance"), ("Crowds", "VisibleDistanceForShadow"),
        ("Crowds", "VisibleDistanceForModel"), ("Crowds", "DepthFadeStart"),
    };

    private static readonly string[] TrackFiles = { @"tracks\anthem\tracksettings.xml", @"tracks\AnthemTrackSettings.xml" };

    private static Dictionary<(string, string), string> Common(bool lod0)
    {
        var d = new Dictionary<(string, string), string>
        {
            [("ForceAnisoFiltering", "value")] = "0",          // Default: let Azimuth's 16x apply
            [("MaxHiDefShadows", "value")] = "16",             // stock free roam / races use 0
            [("CollidableShadows", "value")] = "1",
            [("CrowdDrawShadows", "value")] = "1",
            [("SkipShadowMapUnlessCockpit", "value")] = "0",
            [("EnableWindshieldReflections", "value")] = "1",
            [("HalfRateMirror", "value")] = "0",
            [("MaxCarsInMirror", "value")] = "16",
            [("CollidablesInMirror", "value")] = "1",
            [("CrowdDrawMirror", "value")] = "1",
            [("ParticlesInMirror", "value")] = "1",
            [("CarAICubemap", "value")] = "2",
            [("CarDrawRenderedAO", "value")] = "1",
        };
        if (lod0)
        {
            d[("CarFocusLODMinMax", "min")] = "0";
            d[("CarFocusLODMinMax", "max")] = "0";
        }
        return d;
    }

    public static Dictionary<(string, string), string> BuildQuality(ModSettings s)
    {
        var preset = Presets.FirstOrDefault(p => p.Id == s.Preset) ?? Presets[0];
        var q = preset.Id == "stock" ? new Dictionary<(string, string), string>() : Common(s.PlayerCarLod0);
        if (preset.Id == "stock" && s.PlayerCarLod0)
        {
            q[("CarFocusLODMinMax", "min")] = "0";
            q[("CarFocusLODMinMax", "max")] = "0";
        }
        if (preset.Id != "stock")
        {
            q[("EnvMapFrequencyScale", "value")] = preset.Id == "balanced" ? "1.0" : "3.0";
            q[("ForceMirrorRender", "value")] = preset.Id == "balanced" ? "0" : "1";
        }
        int shadow = s.ShadowResolutionOverride > 0 ? s.ShadowResolutionOverride : preset.Shadow;
        int windshield = s.WindshieldResolutionOverride > 0 ? s.WindshieldResolutionOverride : preset.Windshield;
        if (shadow > 0) q[("ShadowMapResolution", "value")] = shadow.ToString(CultureInfo.InvariantCulture);
        if (windshield > 0) q[("WindshieldReflectionResolution", "value")] = windshield.ToString(CultureInfo.InvariantCulture);
        return q;
    }

    public static string ScenarioOriginalsDir(ModSettings s)
    {
        var userOriginals = Path.Combine(s.MediaDir, "renderscenarios ACTUAL ORIGINAL");
        return Directory.Exists(userOriginals) ? userOriginals : Path.Combine(s.BackupDir, "renderscenarios");
    }

    private static string TrackOriginal(ModSettings s, string rel)
    {
        var legacy = Path.Combine(s.GameRoot, "fh2sql", "patch_backup", rel);
        return File.Exists(legacy) ? legacy : Path.Combine(s.BackupDir, rel);
    }

    /// <summary>Snapshots the current files once, before the tool ever writes them.</summary>
    public static void EnsureOriginals(ModSettings s)
    {
        var scen = ScenarioOriginalsDir(s);
        if (!Directory.Exists(scen))
        {
            Directory.CreateDirectory(scen);
            foreach (var f in Directory.GetFiles(Path.Combine(s.MediaDir, "renderscenarios"), "*.xml"))
                File.Copy(f, Path.Combine(scen, Path.GetFileName(f)));
        }
        foreach (var rel in TrackFiles)
        {
            var orig = TrackOriginal(s, rel);
            var live = Path.Combine(s.MediaDir, rel);
            if (!File.Exists(orig) && File.Exists(live))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(orig)!);
                File.Copy(live, orig);
            }
        }
    }

    public static List<string> Apply(ModSettings s)
    {
        EnsureOriginals(s);
        var log = new List<string>();
        var quality = BuildQuality(s);
        var origDir = ScenarioOriginalsDir(s);
        var liveDir = Path.Combine(s.MediaDir, "renderscenarios");
        foreach (var src in Directory.GetFiles(origDir, "*.xml"))
        {
            var name = Path.GetFileName(src);
            var text = File.ReadAllText(src);
            int changes = 0;
            foreach (var (tag, attr) in ScenarioDistanceFields)
                changes += Scale(ref text, tag, attr, s.DistanceFactor);
            foreach (var ((tag, attr), val) in quality)
            {
                if (Set(ref text, tag, attr, val)) changes++;
                else if (name == "Global.xml" && attr == "value" && !Has(text, tag, attr)) { AddTag(ref text, tag, val); changes++; }
            }
            // every scenario that sets FrameRate (races 60, menus/replays 30) sizes motion blur by it
            if (Set(ref text, "FrameRate", "value", s.MotionBlurFps.ToString(CultureInfo.InvariantCulture))) changes++;
            File.WriteAllText(Path.Combine(liveDir, name), text);
            if (changes > 0) log.Add($"renderscenarios\\{name}: {changes} value(s)");
        }
        foreach (var rel in TrackFiles)
        {
            var orig = TrackOriginal(s, rel);
            if (!File.Exists(orig)) continue;
            var text = File.ReadAllText(orig);
            int changes = TrackDistanceFields.Sum(f => Scale(ref text, f.Tag, f.Attr, s.DistanceFactor));
            File.WriteAllText(Path.Combine(s.MediaDir, rel), text);
            if (changes > 0) log.Add($"{rel}: {changes} distance(s) x{s.DistanceFactor:0.##}");
        }
        return log;
    }

    public static void RestoreStock(ModSettings s)
    {
        EnsureOriginals(s);
        var origDir = ScenarioOriginalsDir(s);
        foreach (var src in Directory.GetFiles(origDir, "*.xml"))
        {
            // the stock 30/60 blur reference makes motion blur far too long at high frame rates, so it is kept
            var text = File.ReadAllText(src);
            Set(ref text, "FrameRate", "value", s.MotionBlurFps.ToString(CultureInfo.InvariantCulture));
            File.WriteAllText(Path.Combine(s.MediaDir, "renderscenarios", Path.GetFileName(src)), text);
        }
        foreach (var rel in TrackFiles)
        {
            var orig = TrackOriginal(s, rel);
            if (File.Exists(orig)) File.Copy(orig, Path.Combine(s.MediaDir, rel), true);
        }
    }

    // File.ReadAllText/WriteAllText keep \r\n untouched, so only the edited numbers change.
    private static Regex AttrRegex(string tag, string attr) =>
        new($"(<{Regex.Escape(tag)}\\b[^>]*?\\b{Regex.Escape(attr)}=\")(-?[0-9.]+)(\")");

    private static bool Has(string text, string tag, string attr) => AttrRegex(tag, attr).IsMatch(text);

    private static bool Set(ref string text, string tag, string attr, string value)
    {
        var rx = AttrRegex(tag, attr);
        var m = rx.Match(text);
        if (!m.Success || m.Groups[2].Value == value) return false;
        text = rx.Replace(text, mm => mm.Groups[1].Value + value + mm.Groups[3].Value, 1);
        return true;
    }

    private static int Scale(ref string text, string tag, string attr, double factor)
    {
        if (Math.Abs(factor - 1.0) < 1e-9) return 0;
        var rx = AttrRegex(tag, attr);
        var m = rx.Match(text);
        if (!m.Success) return 0;
        var old = m.Groups[2].Value;
        var v = double.Parse(old, CultureInfo.InvariantCulture) * factor;
        var decimals = old.Contains('.') ? old.Split('.')[1].Length : -1;
        var formatted = decimals < 0 ? Math.Round(v).ToString(CultureInfo.InvariantCulture) : v.ToString("F" + decimals, CultureInfo.InvariantCulture);
        text = rx.Replace(text, mm => mm.Groups[1].Value + formatted + mm.Groups[3].Value, 1);
        return 1;
    }

    private static void AddTag(ref string text, string tag, string value)
    {
        var nl = text.Contains("\r\n") ? "\r\n" : "\n";
        text = text.Replace("</DynamicRenderSettings>", $"  <{tag} value=\"{value}\"/>{nl}</DynamicRenderSettings>");
    }
}
