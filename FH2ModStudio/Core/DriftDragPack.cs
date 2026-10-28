using System.Globalization;

namespace FH2ModStudio.Core;

/// <summary>
/// Drag tyres (tyre level 4), drift tyres (tyre level 6) and a drift suspension (spring level 5) for every car - FM7's
/// scheme with FH3's drag and drift compounds: one idempotent SQL script, run on the current database and saved as a mod
/// so the game gets it on every start. Sql comes from DriftDragPack.Data.cs (research/modstudio/driftdrag_gen.py); the
/// user's drift alignment (ModSettings.Drift*) is appended as UPDATEs. Steering lock is applied by fh2sql.dll.
/// </summary>
public static partial class DriftDragPack
{
    public const string ModName = "Drift suspension & drag tyres for all cars";

    /// <summary>(cars with drag tyres, cars with drift tyres, cars with a drift suspension, cars in total).</summary>
    public static (int Drag, int DriftTyres, int Drift, int Cars) Count(ICarDb db)
    {
        int N(string sql) => int.TryParse(db.Query(sql, out _)?.Rows.FirstOrDefault()?[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var n) ? n : 0;
        return (N($"SELECT COUNT(DISTINCT Ordinal) FROM List_UpgradeTireCompound WHERE TireCompoundID = {DragCompound};"),
                N($"SELECT COUNT(DISTINCT Ordinal) FROM List_UpgradeTireCompound WHERE TireCompoundID = {DriftCompound};"),
                N("SELECT COUNT(DISTINCT Ordinal) FROM List_UpgradeSpringDamper WHERE Id % 1000 = 905;"),
                N("SELECT COUNT(*) FROM Data_Car;"));
    }

    private static string F(double v) => v.ToString("0.####", CultureInfo.InvariantCulture);

    /// <summary>The drift suspension's alignment (front physics rows end in 905, rear in 995).</summary>
    public static string AlignmentSql(ModSettings s) =>
        $"UPDATE List_SpringDamperPhysics SET StaticCamber = {F(s.DriftFrontCamber)} WHERE SpringDamperPhysicsID % 1000 = 905;\n" +
        $"UPDATE List_SpringDamperPhysics SET StaticCamber = {F(s.DriftRearCamber)}, StaticToe = {F(s.DriftRearToe)} WHERE SpringDamperPhysicsID % 1000 = 995;";

    public static string ComposeSql(ModSettings s) => Sql + "\n" + AlignmentSql(s);

    /// <returns>null on success, otherwise the error.</returns>
    public static string? Apply(ICarDb db, ModSettings s) => db.Execute(ComposeSql(s), ModName);

    public static bool IsSaved(ModSettings s) => s.DbMods.Any(m => m.Name == ModName);

    /// <summary>Brings a saved copy up to date (an older pack version, or other drift values). True when it changed.</summary>
    public static bool UpdateSaved(ModSettings s)
    {
        var old = s.DbMods.FirstOrDefault(m => m.Name == ModName);
        var sql = ComposeSql(s);
        if (old == null || old.Sql == sql) return false;
        old.Sql = sql;
        s.Save();
        return true;
    }

    /// <summary>The shop names and descriptions of the new drift parts live in the game's string tables (all languages):
    /// the porter writes them (fh3port.py upgrade-strings). Needs the game closed. Returns null on success, else why not.</summary>
    public static async Task<string?> WriteShopTextsAsync(ModSettings s)
    {
        var porter = new CarPorter();
        if (!porter.Locate(s)) return "the car porter (fh3port) was not found - the shop shows the drift parts without a name";
        try
        {
            var (code, output) = await porter.CaptureAsync("fh3port.py", "upgrade-strings");
            return code == 0 ? null : CarPorter.Tail(output, 2);
        }
        catch (Exception ex)
        {
            return ex.Message;
        }
    }

    public static void Save(ModSettings s)
    {
        s.DbMods.RemoveAll(m => m.Name == ModName);
        s.DbMods.Add(new DbMod { Name = ModName, Sql = ComposeSql(s), Enabled = true });
        s.Save();
    }

    /// <summary>Drift steering in the running game (fh2sql.dll pipe); used for the next car the game loads.</summary>
    public static string? SendSteering(SqlPipe pipe, ModSettings s)
    {
        var r = pipe.Execute(FormattableString.Invariant($"#drift {s.DriftSteerLock:0.###} {s.DriftSteerSpeed:0.###}"));
        return r.Error;
    }
}
