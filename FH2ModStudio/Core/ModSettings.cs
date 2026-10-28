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
    public string UiPage { get; set; } = "home";
    public double UiLeft { get; set; }
    public double UiTop { get; set; }
    public double UiWidth { get; set; }
    public double UiHeight { get; set; }
    public bool UiMaximized { get; set; }

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

    /// <summary>Finds azimuth.exe and the game folder when the saved ones don't exist: the running Azimuth, its
    /// azimuth.ini (folder= of each game), the folders around this app, then a shallow search of the usual places
    /// (Downloads, Desktop, Documents, Games folders, drive roots). Nothing is assumed about folder names.</summary>
    public void AutoDetectPaths()
    {
        if (NormalizeGameRoot(GameRoot) is { } g) GameRoot = g;
        if (!File.Exists(AzimuthExe)) AzimuthExe = FindAzimuth(GameRoot) ?? AzimuthExe;
        if (!IsGameRoot(GameRoot)) GameRoot = FindGameRoot(AzimuthExe) ?? GameRoot;
        if (!File.Exists(AzimuthExe) && IsGameRoot(GameRoot)) AzimuthExe = FindAzimuth(GameRoot) ?? AzimuthExe;
    }

    /// <summary>The game folder = the one holding Mount\media (Azimuth's game folder, e.g. Anthem_1.0.0.64_x64__...).</summary>
    public static bool IsGameRoot(string? dir) =>
        !string.IsNullOrWhiteSpace(dir) && Directory.Exists(Path.Combine(dir, "Mount", "media"));

    /// <summary>Whatever folder the user picked -> the game folder, or null: the game folder itself, anything inside it
    /// (Mount, media, the exe), or a folder that holds the game folder one or two levels down.</summary>
    public static string? NormalizeGameRoot(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return null;
        path = path.Trim().Trim('"').TrimEnd('\\', '/');
        if (path.Length == 2 && path[1] == ':') path += "\\";
        try
        {
            if (File.Exists(path)) path = Path.GetDirectoryName(path)!;
            if (!Directory.Exists(path)) return null;
            for (var d = new DirectoryInfo(path); d != null; d = d.Parent)
                if (IsGameRoot(d.FullName)) return d.FullName;
            foreach (var sub in SubDirs(path))
            {
                if (IsGameRoot(sub)) return sub;
                foreach (var sub2 in SubDirs(sub))
                    if (IsGameRoot(sub2)) return sub2;
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException) { }
        return null;
    }

    private static IEnumerable<string> SubDirs(string dir)
    {
        try { return Directory.EnumerateDirectories(dir).ToList(); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException) { return Array.Empty<string>(); }
    }

    /// <summary>Folders worth a shallow search, nearest first.</summary>
    private static IEnumerable<string> SearchRoots(params string?[] near)
    {
        foreach (var n in near)
        {
            if (string.IsNullOrWhiteSpace(n)) continue;
            DirectoryInfo? d;
            try { d = new DirectoryInfo(File.Exists(n) ? Path.GetDirectoryName(n)! : n); } catch { continue; }
            for (int i = 0; d != null && i < 4; d = d.Parent, i++) yield return d.FullName;
        }
        string Special(Environment.SpecialFolder f) => Environment.GetFolderPath(f);
        var profile = Special(Environment.SpecialFolder.UserProfile);
        yield return Path.Combine(profile, "Downloads");
        yield return Special(Environment.SpecialFolder.DesktopDirectory);
        yield return Special(Environment.SpecialFolder.MyDocuments);
        yield return profile;
        yield return Special(Environment.SpecialFolder.ProgramFiles);
        yield return Special(Environment.SpecialFolder.ProgramFilesX86);
        foreach (var drive in DriveInfo.GetDrives().Where(x => x.DriveType == DriveType.Fixed && x.IsReady))
        {
            foreach (var games in new[] { "Games", "XboxGames", "Program Files", "Emulators", "Emulation" })
                yield return Path.Combine(drive.RootDirectory.FullName, games);
            yield return drive.RootDirectory.FullName;
        }
    }

    /// <summary>Directories up to <paramref name="depth"/> levels below root (root included), skipping system folders.</summary>
    private static IEnumerable<string> Walk(string root, int depth)
    {
        if (!Directory.Exists(root)) yield break;
        yield return root;
        if (depth == 0) yield break;
        foreach (var sub in SubDirs(root))
        {
            var name = Path.GetFileName(sub);
            if (name.StartsWith('$') || name.StartsWith('.') || name is "Windows" or "AppData" or "node_modules" or "System Volume Information") continue;
            foreach (var d in Walk(sub, depth - 1)) yield return d;
        }
    }

    public static string? FindAzimuth(string? gameRoot)
    {
        try
        {
            var running = GameProcess.FindProcess()?.MainModule?.FileName;
            if (File.Exists(running)) return running;
        }
        catch { }
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var root in SearchRoots(gameRoot, AppDir))
        {
            if (!seen.Add(root)) continue;
            foreach (var d in Walk(root, 2))
            {
                var exe = Path.Combine(d, "azimuth.exe");
                if (File.Exists(exe)) return exe;
            }
        }
        return null;
    }

    /// <summary>Game folders Azimuth knows: folder= lines of data\azimuth.ini (UTF-16; one [title-...] section per game).</summary>
    public static IEnumerable<string> AzimuthGameFolders(string? azimuthExe)
    {
        if (string.IsNullOrEmpty(azimuthExe)) yield break;
        var dir = Path.GetDirectoryName(azimuthExe) ?? "";
        foreach (var ini in new[] { Path.Combine(dir, "data", "azimuth.ini"), Path.Combine(dir, "azimuth.ini") })
        {
            List<string> lines;
            try { lines = File.Exists(ini) ? File.ReadLines(ini).ToList() : new(); } catch (IOException) { continue; }
            foreach (var l in lines.Select(x => x.Trim()))
                if (l.StartsWith("folder=", StringComparison.OrdinalIgnoreCase) && l.Length > 7) yield return l[7..].Trim();
        }
    }

    public static string? FindGameRoot(string? azimuthExe)
    {
        foreach (var f in AzimuthGameFolders(azimuthExe))
            if (NormalizeGameRoot(f) is { } g) return g;
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var root in SearchRoots(AppDir, azimuthExe))
        {
            if (!seen.Add(root)) continue;
            foreach (var d in Walk(root, 2))
                if (IsGameRoot(d)) return d;
        }
        return null;
    }

    public bool PathsValid => File.Exists(AzimuthExe) && IsGameRoot(GameRoot);

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
