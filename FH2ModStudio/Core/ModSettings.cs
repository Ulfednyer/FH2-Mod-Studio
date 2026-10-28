using System.Text;
using System.Text.Json;

namespace FH2ModStudio.Core;

public sealed class DbMod
{
    public string Name { get; set; } = "";
    public string Sql { get; set; } = "";
    public bool Enabled { get; set; } = true;
}

/// <summary>Everything the user chose, persisted next to the exe as JSON.</summary>
public sealed class ModSettings
{
    public string AzimuthExe { get; set; } = "";
    public string GameRoot { get; set; } = "";
    public bool AutoInject { get; set; } = true;

    public string Preset { get; set; } = "ultra";
    public int ShadowResolutionOverride { get; set; }        // 0 = use preset
    public int WindshieldResolutionOverride { get; set; }    // 0 = use preset
    public bool PlayerCarLod0 { get; set; } = true;
    public double DistanceFactor { get; set; } = 2.0;
    public int MotionBlurFps { get; set; } = 120;
    public int Msaa { get; set; } = 8;
    public double BlurDriver { get; set; } = -1;             // -1 = game default
    public double BlurHood { get; set; } = -1;
    public double BlurBumper { get; set; } = -1;

    public List<DbMod> DbMods { get; set; } = new();

    public string PorterDir { get; set; } = "";              // fh2sql\fh3port (FH3 -> FH2 car porter); found automatically
    public bool PortKeepPlates { get; set; }                 // licence plates: FH2 shows them as zeros, hidden by default

    // body-part removal (BodyParts): meshes hidden per car and part, and cars whose .carbin waits for FH2 to close
    public Dictionary<string, Dictionary<string, List<string>>> BodyPartMeshes { get; set; } = new();
    public List<string> BodyPartPending { get; set; } = new();

    // where the user was in the Cars page, restored on the next start
    public string UiCarsCar { get; set; } = "";
    public string UiCarsSection { get; set; } = "";
    public string UiAddKind { get; set; } = "";

    // drift suspension (DriftDragPack): alignment in its physics rows, steering applied by fh2sql.dll while installed
    public double DriftFrontCamber { get; set; } = -5.0;
    public double DriftRearCamber { get; set; } = -1.0;
    public double DriftRearToe { get; set; } = -0.05;
    public double DriftSteerLock { get; set; } = 60.0;      // degrees; 0 = the car's own steering
    public double DriftSteerSpeed { get; set; } = 1.5;      // x the car's steering speeds

    public static string AppDir => AppContext.BaseDirectory;
    public static string SettingsPath => Path.Combine(AppDir, "FH2ModStudio.settings.json");
    public static string DllPath => Path.Combine(AppDir, "fh2sql.dll");
    public static string IniPath => Path.Combine(AppDir, "fh2sql.ini");

    public string MediaDir => Path.Combine(GameRoot, "Mount", "media");
    public string BackupDir => Path.Combine(GameRoot, "FH2ModStudio_backup");

    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };

    public static ModSettings Load()
    {
        ModSettings s;
        try
        {
            s = File.Exists(SettingsPath) ? JsonSerializer.Deserialize<ModSettings>(File.ReadAllText(SettingsPath)) ?? new() : new();
        }
        catch
        {
            s = new();
        }
        s.AutoDetectPaths();
        return s;
    }

    public void Save() => File.WriteAllText(SettingsPath, JsonSerializer.Serialize(this, Json));

    /// <summary>Finds azimuth.exe (running process or known locations) and reads the game folder from azimuth.ini.</summary>
    public void AutoDetectPaths()
    {
        if (!File.Exists(AzimuthExe))
        {
            var running = GameProcess.FindProcess();
            string? path = null;
            try { path = running?.MainModule?.FileName; } catch { }
            var candidates = new[]
            {
                path,
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "amzimuth", "azimuth.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "azimuth", "azimuth.exe"),
            };
            AzimuthExe = candidates.FirstOrDefault(File.Exists) ?? AzimuthExe;
        }
        if (!Directory.Exists(Path.Combine(GameRoot, "Mount")) && File.Exists(AzimuthExe))
        {
            var ini = Path.Combine(Path.GetDirectoryName(AzimuthExe)!, "data", "azimuth.ini");
            if (File.Exists(ini))
            {
                var folder = File.ReadLines(ini).Select(l => l.Trim())
                    .FirstOrDefault(l => l.StartsWith("folder=", StringComparison.OrdinalIgnoreCase) &&
                                         Directory.Exists(Path.Combine(l[7..], "Mount")));
                if (folder != null) GameRoot = folder[7..];
            }
        }
        if (!Directory.Exists(Path.Combine(GameRoot, "Mount")))
        {
            // the tool usually lives in <game>\fh2sql\FH2ModStudio\...
            var dir = new DirectoryInfo(AppDir);
            while (dir != null && !Directory.Exists(Path.Combine(dir.FullName, "Mount"))) dir = dir.Parent;
            if (dir != null) GameRoot = dir.FullName;
        }
    }

    public bool PathsValid => File.Exists(AzimuthExe) && Directory.Exists(MediaDir);

    /// <summary>The frame rate cap set in Azimuth's launcher (frame_rate= in data\azimuth.ini), 0 if unknown.</summary>
    public int AzimuthFrameRate()
    {
        try
        {
            var ini = Path.Combine(Path.GetDirectoryName(AzimuthExe) ?? "", "data", "azimuth.ini");
            var line = File.Exists(ini) ? File.ReadLines(ini).FirstOrDefault(l => l.StartsWith("frame_rate=", StringComparison.OrdinalIgnoreCase)) : null;
            return line != null && int.TryParse(line[11..].Trim(), out var fps) ? fps : 0;
        }
        catch (IOException)
        {
            return 0;
        }
    }

    /// <summary>fh2sql.dll reads this at injection time (MSAA swap + motion blur keeper).</summary>
    public void WriteDllIni()
    {
        static string Blur(string key, double v) => v < 0 ? $";{key}=   (game default)" : FormattableString.Invariant($"{key}={v:0.###}");
        var sb = new StringBuilder();
        sb.AppendLine("; Written by FH2 Mod Studio - edit the values in the app instead.");
        sb.AppendLine("[render]");
        sb.AppendLine($"msaa={Msaa}");
        sb.AppendLine(Blur("blur_driver", BlurDriver));
        sb.AppendLine(Blur("blur_hood", BlurHood));
        sb.AppendLine(Blur("blur_bumper", BlurBumper));
        sb.AppendLine("[drift]");
        sb.AppendLine(FormattableString.Invariant($"steer_lock={DriftSteerLock:0.###}"));
        sb.AppendLine(FormattableString.Invariant($"steer_speed={DriftSteerSpeed:0.###}"));
        File.WriteAllText(IniPath, sb.ToString());
    }
}
