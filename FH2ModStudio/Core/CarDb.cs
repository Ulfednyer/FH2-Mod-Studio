using System.Globalization;
using Microsoft.Data.Sqlite;

namespace FH2ModStudio.Core;

/// <summary>A place car data can be read from / written to: the running game or an offline copy.</summary>
public interface ICarDb
{
    bool IsLive { get; }
    SqlResult? Query(string sql, out string? error);
    /// <returns>null on success, otherwise the error.</returns>
    string? Execute(string sql, string description);
}

public sealed class LiveCarDb : ICarDb
{
    private readonly GameSession _session;
    public LiveCarDb(GameSession session) => _session = session;
    public bool IsLive => true;

    public SqlResult? Query(string sql, out string? error)
    {
        var r = _session.Sql.Execute(sql);
        error = r.Error;
        return r.Ok && r.Results.Count > 0 ? r.Results[0] : null;
    }

    public string? Execute(string sql, string description) => _session.History.Run(sql, description, new List<string>()).Error;
}

/// <summary>SQLite file access via Microsoft.Data.Sqlite: the pristine disk database, or an in-memory working copy.</summary>
public sealed class SqliteCarDb : ICarDb, IDisposable
{
    private readonly SqliteConnection _conn;
    private readonly object _gate = new();
    public bool IsLive => false;

    private SqliteCarDb(SqliteConnection conn)
    {
        _conn = conn;
        _conn.CreateCollation("LOCALIZED_NOCASE", (a, b) => string.Compare(a, b, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>Read-only, lock-free (immutable) view of the database file on disk = true stock values.</summary>
    public static SqliteCarDb OpenStock(string path)
    {
        var uri = new Uri(path).AbsoluteUri + "?immutable=1";
        var conn = new SqliteConnection($"Data Source={uri};Mode=ReadOnly");
        conn.Open();
        return new SqliteCarDb(conn);
    }

    /// <summary>In-memory copy of the stock database with the user's saved mods applied (offline editing).</summary>
    public static SqliteCarDb CreateWorkingCopy(SqliteCarDb stock, IEnumerable<DbMod> mods)
    {
        var mem = new SqliteConnection("Data Source=:memory:");
        mem.Open();
        lock (stock._gate) stock._conn.BackupDatabase(mem);
        var copy = new SqliteCarDb(mem);
        foreach (var m in mods.Where(m => m.Enabled)) copy.Execute(m.Sql, m.Name);
        return copy;
    }

    public SqlResult? Query(string sql, out string? error)
    {
        lock (_gate)
        {
            try
            {
                using var cmd = _conn.CreateCommand();
                cmd.CommandText = sql;
                using var reader = cmd.ExecuteReader();
                var cols = Enumerable.Range(0, reader.FieldCount).Select(reader.GetName).ToList();
                var rows = new List<List<string?>>();
                while (reader.Read())
                    rows.Add(Enumerable.Range(0, reader.FieldCount).Select(i => Format(reader.GetValue(i))).ToList());
                error = null;
                return new SqlResult(cols, rows, false);
            }
            catch (SqliteException ex)
            {
                error = ex.Message;
                return null;
            }
        }
    }

    public string? Execute(string sql, string description)
    {
        lock (_gate)
        {
            try
            {
                using var cmd = _conn.CreateCommand();
                cmd.CommandText = sql;
                cmd.ExecuteNonQuery();
                return null;
            }
            catch (SqliteException ex)
            {
                return ex.Message;
            }
        }
    }

    private static string? Format(object v) => v switch
    {
        DBNull => null,
        double d => d.ToString("R", CultureInfo.InvariantCulture),
        float f => ((double)f).ToString("R", CultureInfo.InvariantCulture),
        long l => l.ToString(CultureInfo.InvariantCulture),
        byte[] => "<blob>",
        _ => Convert.ToString(v, CultureInfo.InvariantCulture),
    };

    public void Dispose()
    {
        lock (_gate) _conn.Dispose();
    }
}
