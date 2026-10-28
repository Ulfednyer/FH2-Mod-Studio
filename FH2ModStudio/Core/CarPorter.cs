using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FH2ModStudio.Core;

/// <summary>One FH3-only car as listed by "batch_port.py cars-json".</summary>
public sealed class Fh3Car
{
    [JsonPropertyName("media")] public string Media { get; set; } = "";
    [JsonPropertyName("make")] public string Make { get; set; } = "";
    [JsonPropertyName("model")] public string Model { get; set; } = "";
    [JsonPropertyName("year")] public JsonElement YearRaw { get; set; }
    [JsonPropertyName("class")] public string Class { get; set; } = "";
    [JsonPropertyName("status")] public string Status { get; set; } = "new";
    [JsonPropertyName("reason")] public string Reason { get; set; } = "";
    [JsonPropertyName("ported_at")] public string PortedAt { get; set; } = "";

    public string Year => YearRaw.ValueKind == JsonValueKind.Number ? YearRaw.GetInt32().ToString() : YearRaw.ToString();
    public string Title => $"{Year} {Make} {Model}".Trim();
    public string StatusText => Status switch
    {
        "ported" => "installed",
        "failed" => "failed before",
        "in_fh2" => "in FH2 - replaces FH2's version",
        _ => "not ported",
    };
    [JsonPropertyName("replaces")] public string Replaces { get; set; } = "";
    public bool ReplacesFh2 => Status == "in_fh2" || Replaces.Length > 0;
    /// <summary>A car zip the user picked on disk; the porter converts this file instead of the media folders' copy.</summary>
    [JsonIgnore] public string? ZipPath { get; set; }
    /// <summary>What port-cars gets for this car: the picked zip's path or the MediaName.</summary>
    public string PortArg => ZipPath ?? Media;
    public string Display => $"{Title}  ·  {Class}  ·  {StatusText}";
    public string SourceText => ZipPath != null ? "from " + ZipPath : "";
    public override string ToString() => Display;
}

/// <summary>Runs the Python FH3 -> FH2 car porter (fh2sql\fh3port) and streams its output.</summary>
public sealed class CarPorter
{
    public string? Dir { get; private set; }
    public string Python { get; private set; } = "py";

    /// <summary>Finds the fh3port folder: saved setting, then walking up from the app folder and the game folder.</summary>
    public bool Locate(ModSettings s)
    {
        var starts = new List<string?> { s.PorterDir, ModSettings.AppDir, s.GameRoot };
        foreach (var start in starts)
        {
            if (string.IsNullOrEmpty(start)) continue;
            if (File.Exists(Path.Combine(start, "fh3port.py")) && File.Exists(Path.Combine(start, "batch_port.py")))
            {
                Dir = start;
                return true;
            }
            for (var d = new DirectoryInfo(start); d != null; d = d.Parent)
            {
                foreach (var rel in new[] { Path.Combine("fh2sql", "fh3port"), "fh3port", Path.Combine("FH3toFH2_CarPort", "fh3port") })
                {
                    var c = Path.Combine(d.FullName, rel);
                    if (File.Exists(Path.Combine(c, "fh3port.py")) && File.Exists(Path.Combine(c, "batch_port.py")))
                    {
                        Dir = c;
                        s.PorterDir = c;
                        return true;
                    }
                }
            }
        }
        Dir = null;
        return false;
    }

    public void UseFolder(string dir, ModSettings s)
    {
        Dir = dir;
        s.PorterDir = dir;
    }

    /// <summary>Runs "python -u &lt;script&gt; args", calling onLine for every output line (on a worker thread).</summary>
    public async Task<int> RunAsync(string script, IEnumerable<string> args, Action<string> onLine, CancellationToken token = default)
    {
        if (Dir == null) throw new InvalidOperationException("The car porter folder (fh3port) was not found.");
        foreach (var py in new[] { Python, "py", "python" }.Distinct())
        {
            var psi = new ProcessStartInfo(py)
            {
                WorkingDirectory = Dir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            psi.ArgumentList.Add("-u");
            psi.ArgumentList.Add(script);
            foreach (var a in args) psi.ArgumentList.Add(a);
            psi.Environment["PYTHONIOENCODING"] = "utf-8";
            psi.Environment["PYTHONUNBUFFERED"] = "1";
            Process proc;
            try
            {
                proc = Process.Start(psi)!;
            }
            catch (System.ComponentModel.Win32Exception)
            {
                continue;   // this launcher is not installed, try the next
            }
            Python = py;
            using (proc)
            using (token.Register(() => { try { proc.Kill(true); } catch { } }))
            {
                proc.OutputDataReceived += (_, e) => { if (e.Data != null) onLine(e.Data); };
                proc.ErrorDataReceived += (_, e) => { if (e.Data != null) onLine(e.Data); };
                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                await proc.WaitForExitAsync(CancellationToken.None);
                return proc.ExitCode;
            }
        }
        throw new InvalidOperationException("Python was not found. Close FH2 Mod Studio, delete prerequisites.ok next to it and start it with \"Start FH2 Mod Studio.cmd\" - that installs Python and puts it on PATH. Or install Python 3 from python.org with \"Add to PATH\" ticked.");
    }

    /// <summary>Runs a command and returns its whole output.</summary>
    public async Task<(int Code, string Output)> CaptureAsync(string script, params string[] args)
    {
        var sb = new StringBuilder();
        var code = await RunAsync(script, args, l => { lock (sb) sb.AppendLine(l); });
        return (code, sb.ToString());
    }

    /// <summary>Paths the porter uses (fh3port.ini, with its defaults): game, fh3, converter and *_ok flags.</summary>
    public async Task<JsonElement?> LoadPathsAsync()
    {
        var (code, output) = await CaptureAsync("fh3port.py", "paths");
        var line = output.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("{"));
        return code == 0 && line != null ? JsonDocument.Parse(line).RootElement.Clone() : null;
    }

    /// <summary>Sets one [paths] key of fh3port.ini (game = FH2 folder with Mount, fh3 = FH3 installation, converter).</summary>
    public void SetPath(string key, string value)
    {
        if (Dir == null) return;
        var ini = Path.Combine(Dir, "fh3port.ini");
        var lines = File.Exists(ini) ? File.ReadAllLines(ini).ToList() : new List<string>();
        int section = lines.FindIndex(l => l.Trim().Equals("[paths]", StringComparison.OrdinalIgnoreCase));
        if (section < 0)
        {
            lines.Add("[paths]");
            section = lines.Count - 1;
        }
        int end = lines.FindIndex(section + 1, l => l.TrimStart().StartsWith("["));
        if (end < 0) end = lines.Count;
        int at = lines.FindIndex(section + 1, end - section - 1,
            l => l.Split('=')[0].Trim().Equals(key, StringComparison.OrdinalIgnoreCase));
        if (at >= 0) lines[at] = $"{key} = {value}";
        else lines.Insert(end, $"{key} = {value}");
        File.WriteAllLines(ini, lines);
    }

    public async Task<List<Fh3Car>> LoadCarsAsync()
    {
        var (code, output) = await CaptureAsync("batch_port.py", "cars-json");
        var line = output.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("["));
        if (code != 0 || line == null)
            throw new InvalidOperationException("Could not read the car list:\n" + Tail(output));
        return JsonSerializer.Deserialize<List<Fh3Car>>(line) ?? new();
    }

    public static string Tail(string s, int lines = 8) =>
        string.Join("\n", s.Split('\n').Select(l => l.TrimEnd()).Where(l => l.Length > 0).TakeLast(lines));
}
