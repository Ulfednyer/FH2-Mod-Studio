using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace FH2ModStudio.Core;

public sealed record SqlResult(List<string> Columns, List<List<string?>> Rows, bool Truncated);

public sealed record SqlResponse(List<SqlResult> Results, string? Error, string? Info)
{
    public bool Ok => Error == null;
}

/// <summary>Client for fh2sql.dll's pipe: frames are u32 little-endian length + UTF-8; replies are JSON.</summary>
public sealed class SqlPipe : IDisposable
{
    private readonly object _gate = new();
    private NamedPipeClientStream? _pipe;

    public SqlResponse Execute(string sql)
    {
        lock (_gate)
        {
            for (int attempt = 0; ; attempt++)
            {
                try
                {
                    if (_pipe is not { IsConnected: true })
                    {
                        _pipe?.Dispose();
                        _pipe = new NamedPipeClientStream(".", Injector.PipeName, PipeDirection.InOut);
                        _pipe.Connect(1500);
                    }
                    var payload = Encoding.UTF8.GetBytes(sql);
                    _pipe.Write(BitConverter.GetBytes(payload.Length));
                    _pipe.Write(payload);
                    _pipe.Flush();
                    var len = BitConverter.ToInt32(ReadExact(4));
                    return Parse(Encoding.UTF8.GetString(ReadExact(len)));
                }
                catch (Exception ex) when (ex is IOException or TimeoutException or ObjectDisposedException)
                {
                    _pipe?.Dispose();
                    _pipe = null;
                    if (attempt >= 1)
                        return new SqlResponse(new(), "The mod DLL is not reachable. Start the game with mods (Home page).", null);
                }
            }
        }
    }

    public Task<SqlResponse> ExecuteAsync(string sql) => Task.Run(() => Execute(sql));

    private byte[] ReadExact(int n)
    {
        var buf = new byte[n];
        int got = 0;
        while (got < n)
        {
            int r = _pipe!.Read(buf, got, n - got);
            if (r == 0) throw new IOException("pipe closed");
            got += r;
        }
        return buf;
    }

    private static SqlResponse Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        var results = new List<SqlResult>();
        if (root.TryGetProperty("results", out var rs))
        {
            foreach (var r in rs.EnumerateArray())
            {
                var cols = r.GetProperty("columns").EnumerateArray().Select(c => c.GetString() ?? "").ToList();
                var rows = r.GetProperty("rows").EnumerateArray()
                    .Select(row => row.EnumerateArray().Select(v => v.ValueKind == JsonValueKind.Null ? null : v.GetString()).ToList())
                    .ToList();
                results.Add(new SqlResult(cols, rows, r.TryGetProperty("truncated", out var t) && t.GetBoolean()));
            }
        }
        string? error = root.TryGetProperty("error", out var e) && e.ValueKind == JsonValueKind.String ? e.GetString() : null;
        string? info = root.TryGetProperty("info", out var i) && i.ValueKind == JsonValueKind.String ? i.GetString() : null;
        return new SqlResponse(results, error, info);
    }

    public void Dispose()
    {
        lock (_gate)
        {
            _pipe?.Dispose();
            _pipe = null;
        }
    }
}
