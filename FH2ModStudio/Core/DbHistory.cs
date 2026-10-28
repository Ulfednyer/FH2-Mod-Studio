using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace FH2ModStudio.Core;

public sealed class DbChange
{
    public DateTime Time { get; init; } = DateTime.Now;
    public string Description { get; init; } = "";
    public string Sql { get; init; } = "";
    public string? UndoSql { get; init; }
    public bool Undone { get; set; }
    public bool CanUndo => UndoSql != null && !Undone;
    public string TimeText => Time.ToString("HH:mm:ss");
    public string State => Undone ? "Undone" : UndoSql == null ? "Can't be undone" : "";
}

/// <summary>Runs data-changing SQL and records an exact inverse so every change can be undone.</summary>
public sealed class DbHistory
{
    private readonly SqlPipe _sql;
    public List<DbChange> Changes { get; } = new();

    public DbHistory(SqlPipe sql) => _sql = sql;

    private static readonly Regex UpdateRx = new(@"^\s*UPDATE\s+(?<t>""[^""]+""|\[[^\]]+\]|\w+)\s+SET\s+.+?(?:\s+WHERE\s+(?<w>.+?))?\s*;?\s*$",
        RegexOptions.IgnoreCase | RegexOptions.Singleline);
    private static readonly Regex DeleteRx = new(@"^\s*DELETE\s+FROM\s+(?<t>""[^""]+""|\[[^\]]+\]|\w+)(?:\s+WHERE\s+(?<w>.+?))?\s*;?\s*$",
        RegexOptions.IgnoreCase | RegexOptions.Singleline);
    private static readonly Regex InsertRx = new(@"^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(?<t>""[^""]+""|\[[^\]]+\]|\w+)",
        RegexOptions.IgnoreCase);

    public static bool IsReadOnly(string sql)
    {
        var s = sql.TrimStart().ToUpperInvariant();
        return s.StartsWith("SELECT") || s.StartsWith("PRAGMA") || s.StartsWith("EXPLAIN") || s.StartsWith("WITH");
    }

    /// <summary>Splits a script into statements on ';' outside quotes.</summary>
    public static List<string> SplitStatements(string script)
    {
        var list = new List<string>();
        var sb = new StringBuilder();
        char? quote = null;
        foreach (var c in script)
        {
            if (quote == null && (c == '\'' || c == '"')) quote = c;
            else if (quote == c) quote = null;
            if (c == ';' && quote == null)
            {
                if (sb.ToString().Trim().Length > 0) list.Add(sb.ToString().Trim());
                sb.Clear();
            }
            else sb.Append(c);
        }
        if (sb.ToString().Trim().Length > 0) list.Add(sb.ToString().Trim());
        return list;
    }

    public static string Literal(string? v)
    {
        if (v == null) return "NULL";
        if (Regex.IsMatch(v, @"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")) return v;
        return "'" + v.Replace("'", "''") + "'";
    }

    public static string QuoteIdent(string name) => "\"" + name.Replace("\"", "\"\"") + "\"";

    /// <summary>Builds the inverse of one data-changing statement by snapshotting affected rows first.</summary>
    private string? BuildUndo(string stmt, out string? warning)
    {
        warning = null;
        Match m;
        if ((m = UpdateRx.Match(stmt)).Success || (m = DeleteRx.Match(stmt)).Success)
        {
            bool isUpdate = stmt.TrimStart().StartsWith("UPDATE", StringComparison.OrdinalIgnoreCase);
            var table = m.Groups["t"].Value;
            var where = m.Groups["w"].Success ? " WHERE " + m.Groups["w"].Value : "";
            var snap = _sql.Execute($"SELECT rowid AS __rowid, * FROM {table}{where};");
            if (!snap.Ok || snap.Results.Count == 0) { warning = "could not snapshot rows for undo: " + snap.Error; return null; }
            var r = snap.Results[0];
            if (r.Truncated) { warning = "too many rows to record an undo"; return null; }
            var cols = r.Columns.Skip(1).ToList();
            var sb = new StringBuilder();
            foreach (var row in r.Rows)
            {
                if (isUpdate)
                    sb.Append($"UPDATE {table} SET {string.Join(", ", cols.Select((c, i) => $"{QuoteIdent(c)}={Literal(row[i + 1])}"))} WHERE rowid={row[0]};\n");
                else
                    sb.Append($"INSERT INTO {table} (rowid, {string.Join(", ", cols.Select(QuoteIdent))}) VALUES ({row[0]}, {string.Join(", ", row.Skip(1).Select(Literal))});\n");
            }
            return sb.ToString();
        }
        if ((m = InsertRx.Match(stmt)).Success)
        {
            var table = m.Groups["t"].Value;
            var max = _sql.Execute($"SELECT IFNULL(MAX(rowid), 0) FROM {table};");
            if (!max.Ok || max.Results.Count == 0) { warning = "could not record an undo for the insert"; return null; }
            return $"DELETE FROM {table} WHERE rowid > {max.Results[0].Rows[0][0]};\n";
        }
        warning = "this kind of statement cannot be undone";
        return null;
    }

    /// <summary>Executes a script; data-changing statements are recorded with undo. Returns the last response.</summary>
    public SqlResponse Run(string script, string description, List<string> warnings)
    {
        SqlResponse last = new(new(), null, null);
        var undoParts = new List<string>();
        var changed = new List<string>();
        bool fullyUndoable = true;   // a partial undo would be misleading, so it is all or nothing
        foreach (var stmt in SplitStatements(script))
        {
            if (!IsReadOnly(stmt))
            {
                var undo = BuildUndo(stmt, out var warn);
                if (warn != null) warnings.Add(warn);
                if (undo != null) undoParts.Insert(0, undo);   // reverse order on undo
                else fullyUndoable = false;
                changed.Add(stmt);
            }
            last = _sql.Execute(stmt);
            if (!last.Ok) break;
        }
        if (changed.Count > 0)
            Changes.Insert(0, new DbChange
            {
                Description = description,
                Sql = string.Join(";\n", changed) + ";",
                UndoSql = fullyUndoable && undoParts.Count > 0 && last.Ok ? string.Concat(undoParts) : null,
            });
        return last;
    }

    public SqlResponse Undo(DbChange change)
    {
        var r = _sql.Execute(change.UndoSql!);
        if (r.Ok) change.Undone = true;
        return r;
    }
}
