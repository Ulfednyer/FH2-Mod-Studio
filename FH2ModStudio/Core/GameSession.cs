using System.Diagnostics;
using System.Windows.Threading;

namespace FH2ModStudio.Core;

public sealed record SessionStatus(GameState Game, bool ModsLoaded, bool DatabaseReady, int Pid, string? Message);

/// <summary>
/// Polls the game once a second, injects fh2sql.dll as soon as Azimuth starts (so launch-time settings like MSAA
/// always apply) and re-applies the user's saved database mods once per game session.
/// </summary>
public sealed class GameSession : IDisposable
{
    private readonly ModSettings _settings;
    private readonly DispatcherTimer _timer;
    private readonly HashSet<int> _injected = new();
    private readonly HashSet<int> _modsApplied = new();
    private bool _busy;

    public SqlPipe Sql { get; } = new();
    public DbHistory History { get; }
    public LiveSettings Live { get; } = new();
    public GameProcess? Game { get; private set; }
    public SessionStatus Status { get; private set; } = new(GameState.NotRunning, false, false, 0, null);

    public event Action<SessionStatus>? StatusChanged;

    public GameSession(ModSettings settings)
    {
        _settings = settings;
        History = new DbHistory(Sql);
        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timer.Tick += async (_, _) => await PollAsync();
        _timer.Start();
    }

    public async Task PollAsync()
    {
        if (_busy) return;
        _busy = true;
        try
        {
            var status = await Task.Run(Probe);
            Status = status;
            StatusChanged?.Invoke(status);
        }
        finally
        {
            _busy = false;
        }
    }

    private SessionStatus Probe()
    {
        if (Game != null && Game.HasExited)
        {
            Game.Dispose();
            Game = null;
            Sql.Dispose();
        }
        Game ??= GameProcess.TryOpen();
        if (Game == null) return new SessionStatus(GameState.NotRunning, false, false, 0, null);

        string? message = null;
        bool loaded = Injector.IsDllLoaded();
        if (!loaded && _settings.AutoInject && _injected.Add(Game.Pid))
        {
            _settings.WriteDllIni();
            message = Injector.Inject(Game.Pid, ModSettings.DllPath) is { } err ? "Injection failed: " + err : "Mods loaded into Azimuth";
            loaded = Injector.IsDllLoaded();
        }
        var state = Game.IsGameLoaded ? GameState.InGame : GameState.Launcher;
        bool dbReady = false;
        if (loaded && state == GameState.InGame)
        {
            var info = Sql.Execute("!info").Info ?? "";
            dbReady = info.Contains("sqlite3=") && !info.Contains("sqlite3=0000000000000000") && !info.Contains('|');
        }
        if (dbReady && _modsApplied.Add(Game.Pid))
        {
            var enabled = _settings.DbMods.Where(m => m.Enabled).ToList();
            if (enabled.Count > 0)
            {
                var failed = enabled.Where(m => !Sql.Execute(m.Sql).Ok).Select(m => m.Name).ToList();
                message = failed.Count == 0
                    ? $"Applied {enabled.Count} saved database mod(s)"
                    : $"Saved mods failed: {string.Join(", ", failed)}";
            }
        }
        return new SessionStatus(state, loaded, dbReady, Game.Pid, message);
    }

    /// <summary>Starts Azimuth; injection happens automatically on the next poll.</summary>
    public string? LaunchAzimuth()
    {
        if (GameProcess.FindProcess() != null) return null;
        if (!File.Exists(_settings.AzimuthExe)) return "Azimuth not found. Set its location under Setup.";
        _settings.WriteDllIni();
        Process.Start(new ProcessStartInfo(_settings.AzimuthExe) { WorkingDirectory = Path.GetDirectoryName(_settings.AzimuthExe)!, UseShellExecute = true });
        return null;
    }

    public string? InjectNow()
    {
        if (Game == null) return "Azimuth is not running.";
        _settings.WriteDllIni();
        _injected.Add(Game.Pid);
        return Injector.Inject(Game.Pid, ModSettings.DllPath);
    }

    public void Dispose()
    {
        _timer.Stop();
        Sql.Dispose();
        Game?.Dispose();
    }
}
