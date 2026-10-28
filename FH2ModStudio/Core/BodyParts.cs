using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FH2ModStudio.Core;

public sealed record BodyPart(string Key, string Label, string Table, string RemoveLabel);

/// <summary>Meshes of a car's .carbin as "bodyparts.py list" reports them.</summary>
public sealed class CarMeshes
{
    /// <summary>Always-drawn meshes (body part): what a removal can hide.</summary>
    [JsonPropertyName("meshes")] public List<string> Meshes { get; set; } = new();
    /// <summary>Upgradable part id -> meshes already tied to upgrade rows (hidden by any new row on their own).</summary>
    [JsonPropertyName("tagged")] public Dictionary<string, List<string>> Tagged { get; set; } = new();
    [JsonPropertyName("suggest")] public Dictionary<string, List<string>> Suggest { get; set; } = new();
    [JsonPropertyName("parts")] public Dictionary<string, int> Parts { get; set; } = new();
}

/// <summary>A car make's brand in the upgrade shop (List_PartManufacturer), from "bodyparts.py make".</summary>
public sealed class MakeBrand
{
    [JsonPropertyName("name")] public string? Name { get; set; }
    [JsonPropertyName("part_manufacturer")] public long? PartManufacturer { get; set; }
    [JsonPropertyName("decal")] public string? Decal { get; set; }
}

/// <summary>
/// Body-part removal upgrades (hood, bumpers, side skirts, rear wing). The shop row alone can only hide meshes the
/// car's .carbin ties to upgrade rows; most cars draw hood, bumpers and skirts as part of the always-drawn body. The
/// porter's bodyparts.py moves the chosen meshes into the part's upgrade list (tagged with every row but the removal
/// rows) - that rewrites the car zip, so it runs only while FH2 is closed. Rows with RequiresGraphics = 0 are removals,
/// like FH2's own (POR_911GT2_95 rear wing level 4).
/// </summary>
public static class BodyParts
{
    public const string CatalogModName = "Upgrade catalog (shared rows)";

    public static readonly BodyPart[] Parts =
    {
        new("hood", "Hood", "List_UpgradeCarBodyHood", "Remove hood"),
        new("front_bumper", "Front bumper", "List_UpgradeCarBodyFrontBumper", "Remove front bumper"),
        new("rear_bumper", "Rear bumper", "List_UpgradeCarBodyRearBumper", "Remove rear bumper"),
        new("rear_wing", "Rear wing", "List_UpgradeRearWing", "Remove rear wing"),
        new("side_skirts", "Side skirts", "List_UpgradeCarBodySideSkirt", "Remove side skirts"),
    };

    public static bool IsPartTable(string? table) => table != null && Parts.Any(p => p.Table.Equals(table, StringComparison.OrdinalIgnoreCase));

    public static string? Where(BodyPart p, CarIds ids) =>
        p.Key == "rear_wing" ? $"Ordinal = {ids.CarId}" : ids.BodyId is { } b ? $"CarBodyId = {b}" : null;

    private static string Lit(string s) => DbHistory.Literal(s);

    private static string? LastJson(string output) =>
        output.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("{"));

    public static async Task<CarMeshes?> ListMeshesAsync(CarPorter porter, string media)
    {
        var (code, output) = await porter.CaptureAsync("bodyparts.py", "list", media);
        var line = LastJson(output);
        if (code != 0 || line == null) throw new InvalidOperationException("Could not read the car's meshes: " + CarPorter.Tail(output, 2));
        return JsonSerializer.Deserialize<CarMeshes>(line);
    }

    public static async Task<MakeBrand> MakeAsync(CarPorter porter, long makeId)
    {
        var (code, output) = await porter.CaptureAsync("bodyparts.py", "make", makeId.ToString(CultureInfo.InvariantCulture));
        var line = LastJson(output);
        return code == 0 && line != null ? JsonSerializer.Deserialize<MakeBrand>(line) ?? new() : new();
    }

    /// <summary>The List_PartManufacturer Id for the car's make, plus SQL adding a row for makes FH2 has none for
    /// (plain name like FH2's DLC rows 'Rocket Bunny' / 'RWB'; logo = the make's livery decal, else the Stock logo).</summary>
    public static (long Id, string Sql) Brand(ICarDb db, MakeBrand brand)
    {
        if (brand.PartManufacturer is { } known) return (known, "");
        if (string.IsNullOrWhiteSpace(brand.Name)) return (1, "");   // 1 = "Stock"
        var name = brand.Name.Trim();
        var have = db.Query($"SELECT Id FROM List_PartManufacturer WHERE PartManufacturer = {Lit(name)};", out _);
        if (have is { Rows.Count: > 0 } && long.TryParse(have.Rows[0][0], out var existing)) return (existing, "");
        var maxRow = db.Query("SELECT MAX(Id) FROM List_PartManufacturer;", out _);
        long id = Math.Max(1000, (maxRow is { Rows.Count: > 0 } && long.TryParse(maxRow.Rows[0][0], out var m) ? m : 0) + 1);
        var logo = brand.Decal;
        if (logo == null)
        {
            var stock = db.Query("SELECT LogoPath FROM List_PartManufacturer WHERE Id = 1;", out _);
            logo = stock is { Rows.Count: > 0 } ? stock.Rows[0][0] ?? "decal364" : "decal364";
        }
        return (id, $"INSERT OR IGNORE INTO List_PartManufacturer (Id, PartManufacturer, LogoPath) VALUES ({id}, {Lit(name)}, {Lit(logo)});\n");
    }

    /// <summary>Rows shared by every car (shop catalog entries, brands) live in one saved mod, so they come back on
    /// every launch like the per-car mods that point at them. Statements must be idempotent (INSERT OR IGNORE).</summary>
    public static void AddToCatalog(ModSettings s, string sql)
    {
        var lines = sql.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0)
                       .Select(l => l.StartsWith("INSERT INTO", StringComparison.OrdinalIgnoreCase) ? "INSERT OR IGNORE INTO" + l[11..] : l).ToList();
        if (lines.Count == 0) return;
        var mod = s.DbMods.FirstOrDefault(m => m.Name == CatalogModName);
        if (mod == null)
        {
            mod = new DbMod { Name = CatalogModName, Sql = "", Enabled = true };
            s.DbMods.Insert(0, mod);
        }
        var have = mod.Sql.Split('\n').Select(l => l.Trim()).ToHashSet();
        var add = lines.Where(l => have.Add(l)).ToList();
        if (add.Count == 0) return;
        mod.Sql = (mod.Sql.TrimEnd() + "\n" + string.Join("\n", add)).Trim() + "\n";
        mod.Enabled = true;
        s.Save();
    }

    public static List<string> SavedMeshes(ModSettings s, string media, string part) =>
        s.BodyPartMeshes.TryGetValue(media, out var parts) && parts.TryGetValue(part, out var list) ? list : new();

    public static void SaveMeshes(ModSettings s, string media, string part, List<string> meshes)
    {
        if (!s.BodyPartMeshes.TryGetValue(media, out var parts)) s.BodyPartMeshes[media] = parts = new();
        parts[part] = meshes;
        s.Save();
    }

    private sealed record Rows(BodyPart Part, List<long[]> List);

    private static List<Rows> PartRows(ICarDb db, CarIds ids)
    {
        var all = new List<Rows>();
        foreach (var p in Parts)
        {
            if (Where(p, ids) is not { } where) continue;
            var r = db.Query($"SELECT Id, Level, IsStock, RequiresGraphics FROM {DbHistory.QuoteIdent(p.Table)} WHERE {where} ORDER BY Level, Id;", out _);
            var list = r?.Rows.Select(row => row.Select(v => long.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out var x) ? x : 1).ToArray()).ToList() ?? new();
            all.Add(new Rows(p, list));
        }
        return all;
    }

    /// <summary>Whether the car's .carbin needs rebuilding: saved mesh choices, removal rows, or rows the stock game
    /// doesn't have (a level added as a copy: the .carbin doesn't know its Id, so the part would vanish at that level).</summary>
    public static bool Relevant(ICarDb db, ICarDb stock, CarIds ids, ModSettings s)
    {
        if (s.BodyPartMeshes.ContainsKey(ids.Media)) return true;
        var now = PartRows(db, ids);
        if (now.Any(r => r.List.Any(x => x[3] == 0))) return true;
        var stockIds = PartRows(stock, ids).SelectMany(r => r.List.Select(x => x[0])).ToHashSet();
        return now.Any(r => r.List.Any(x => !stockIds.Contains(x[0])));
    }

    /// <summary>Rebuilds the car's .carbin from its original for the current rows (FH2 must be closed). Returns a
    /// short summary, or throws with the porter's message.</summary>
    public static async Task<string> SyncAsync(CarPorter porter, ICarDb db, CarIds ids, ModSettings s)
    {
        var rows = await Task.Run(() => PartRows(db, ids));
        CarMeshes? meshes = null;
        var parts = new List<object>();
        foreach (var r in rows)
        {
            bool removal = r.List.Any(x => x[3] == 0);
            var models = SavedMeshes(s, ids.Media, r.Part.Key);
            if (removal && models.Count == 0 && !(s.BodyPartMeshes.TryGetValue(ids.Media, out var p) && p.ContainsKey(r.Part.Key)))
            {
                meshes ??= await ListMeshesAsync(porter, ids.Media);
                models = meshes?.Suggest.GetValueOrDefault(r.Part.Key) ?? new();
            }
            parts.Add(new { part = r.Part.Key, body = ids.BodyId ?? -1, rows = r.List, models });
        }
        var spec = Path.Combine(Path.GetTempPath(), $"fh2ms_bodyparts_{ids.Media}.json");
        await File.WriteAllTextAsync(spec, JsonSerializer.Serialize(new { parts }));
        try
        {
            var (code, output) = await porter.CaptureAsync("bodyparts.py", "apply", ids.Media, spec);
            var line = LastJson(output);
            if (code != 0 || line == null) throw new InvalidOperationException(CarPorter.Tail(output, 3));
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            bool changed = root.TryGetProperty("changed", out var c) && c.GetBoolean();
            if (root.TryGetProperty("restored", out _)) return changed ? "car file back to original" : "car file unchanged";
            var hidden = new List<string>();
            if (root.TryGetProperty("report", out var rep))
                foreach (var e in rep.EnumerateArray())
                    if (e.GetProperty("removal").GetArrayLength() > 0)
                        hidden.Add(Parts.First(p => p.Key == e.GetProperty("part").GetString()).Label.ToLowerInvariant());
            return !changed ? "car file already up to date" : hidden.Count > 0 ? "car file updated - removable: " + string.Join(", ", hidden) : "car file updated";
        }
        finally
        {
            try { File.Delete(spec); } catch { }
        }
    }

    public static bool GameRunning => GameProcess.FindProcess() != null;
}
