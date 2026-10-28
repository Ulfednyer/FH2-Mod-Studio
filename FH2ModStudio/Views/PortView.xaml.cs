using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using FH2ModStudio.Core;

namespace FH2ModStudio.Views;

public sealed class PortResultRow
{
    public string Glyph { get; init; } = "";
    public Brush Color { get; init; } = Brushes.Gray;
    public string Title { get; init; } = "";
    public string Detail { get; init; } = "";
}

/// <summary>Pick FH3-only cars from a list and run the Python porter (batch_port.py port-cars) on them.</summary>
public partial class PortView : UserControl
{
    private static readonly Brush Green = new SolidColorBrush(Color.FromRgb(0x34, 0xC7, 0x59));
    private static readonly Brush Red = new SolidColorBrush(Color.FromRgb(0xFF, 0x3B, 0x30));
    private static readonly Brush Orange = new SolidColorBrush(Color.FromRgb(0xFF, 0x95, 0x00));
    private static readonly Brush Grey = new SolidColorBrush(Color.FromRgb(0x8E, 0x8E, 0x93));

    private MainWindow _main = null!;
    private readonly CarPorter _porter = new();
    private List<Fh3Car> _cars = new();
    private readonly ObservableCollection<Fh3Car> _chosen = new();
    private readonly ObservableCollection<PortResultRow> _results = new();
    private SessionStatus _status = new(GameState.NotRunning, false, false, 0, null);
    private bool _setupOk, _busy, _loaded;
    private string? _snapshot;
    private readonly StringBuilder _pending = new();
    private readonly DispatcherTimer _logTimer;

    public PortView()
    {
        InitializeComponent();
        ChosenList.ItemsSource = _chosen;
        ResultList.ItemsSource = _results;
        _logTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) };
        _logTimer.Tick += (_, _) => FlushLog();
    }

    public void Init(MainWindow main)
    {
        _main = main;
        PlatesCheck.IsChecked = main.Settings.PortKeepPlates;
        _porter.Locate(main.Settings);
    }

    public async void OnShown()
    {
        if (!_loaded && !_busy) await CheckSetupAsync();
    }

    public void OnStatus(SessionStatus s)
    {
        _status = s;
        UpdateRunState();
    }

    // ───────────── porter setup ─────────────

    private async Task CheckSetupAsync()
    {
        _setupOk = false;
        SetSetup(Grey, "Checking the porter…", "");
        if (_porter.Dir == null && !_porter.Locate(_main.Settings))
        {
            SetSetup(Red, "Car porter not found",
                "FH2 Mod Studio looks for the fh3port folder (with fh3port.py) next to itself and the game. Use \"Choose folder…\" to point at it.");
            UpdateRunState();
            return;
        }
        _busy = true;
        UpdateRunState();
        try
        {
            // every porter command needs numpy; without it even the paths below came back empty ("not set")
            var (pathsCode, pathsOut) = await _porter.CaptureAsync("fh3port.py", "paths");
            if (pathsCode != 0 && CarPorter.NumpyMissing(pathsOut))
            {
                SetSetup(Grey, "Installing numpy for Python…", "The car porter needs the Python package numpy. This takes a minute.");
                var err = await _porter.InstallNumpyAsync(_ => { });
                if (err != null)
                {
                    SetSetup(Red, "numpy could not be installed",
                        err + "\nClose FH2 Mod Studio, delete prerequisites.ok next to it and start \"Start FH2 Mod Studio.cmd\" again (it writes setup.log), " +
                        "or run in a command prompt: py -m pip install numpy");
                    return;
                }
                (pathsCode, pathsOut) = await _porter.CaptureAsync("fh3port.py", "paths");
            }
            // the game folder set on the Home page is the porter's too
            var line = pathsOut.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("{"));
            if (line != null && JsonDocument.Parse(line).RootElement.TryGetProperty("game_ok", out var gameOk) && !gameOk.GetBoolean()
                && ModSettings.IsGameRoot(_main.Settings.GameRoot))
                _porter.SetPath("game", _main.Settings.GameRoot);
            await ShowPathsAsync();
            var (code, output) = await _porter.CaptureAsync("fh3port.py", "setup");
            var lines = output.Split('\n').Select(l => l.TrimEnd()).Where(l => l.Length > 0).ToList();
            var bad = lines.Where(l => l.Contains(" MISSING") || l.Contains(" missing") || l.Contains("not found")).ToList();
            if (code != 0 || !lines.Any(l => l.Trim() == "setup ok"))
            {
                SetSetup(Red, "The porter is not set up yet", string.Join("\n", (bad.Count > 0 ? bad : lines.TakeLast(6)))
                    + "\nSet the FH2 / FH3 / converter paths in fh3port.ini in " + _porter.Dir);
                return;
            }
            _cars = await _porter.LoadCarsAsync();
            _loaded = true;
            _setupOk = true;
            int ported = _cars.Count(c => c.Status == "ported"), failed = _cars.Count(c => c.Status == "failed");
            SetSetup(Green, "Porter ready",
                $"{_cars.Count} FH3 cars: {ported} installed, {failed} failed before, {_cars.Count(c => c.Status == "new")} not in FH2 and not ported yet, " +
                $"{_cars.Count(c => c.Status == "in_fh2")} also in FH2 (can replace FH2's version).  Python: {_porter.Python}  ·  {_porter.Dir}");
            ApplyFilter();
        }
        catch (Exception ex)
        {
            SetSetup(Red, "The porter could not start", ex.Message);
        }
        finally
        {
            _busy = false;
            UpdateRunState();
        }
    }

    private async Task ShowPathsAsync()
    {
        var p = await _porter.LoadPathsAsync();
        void Show(TextBlock t, string key)
        {
            var value = p?.TryGetProperty(key, out var v) == true ? v.GetString() ?? "" : "";
            var ok = p?.TryGetProperty(key + "_ok", out var o) == true && o.GetBoolean();
            t.Text = value.Length == 0 ? "not set" : ok ? value : value + "   (not found)";
            t.Foreground = ok ? (Brush)FindResource("TextSecondary") : Red;
            t.ToolTip = value;
        }
        Show(Fh2PathTxt, "game");
        Show(Fh3PathTxt, "fh3");
        Show(Fh3ExtraTxt, "fh3_extra");
        if (Fh3ExtraTxt.Text == "not set") Fh3ExtraTxt.Text = "none (optional)";
        Show(CliPathTxt, "converter");
    }

    private async void BrowsePath_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _porter.Dir == null || (sender as FrameworkElement)?.Tag is not string key) return;
        string? chosen = null;
        if (key == "converter")
        {
            var dlg = new Microsoft.Win32.OpenFileDialog { Title = "ForzaToolsCli.exe", Filter = "ForzaToolsCli.exe|ForzaToolsCli.exe|Programs (*.exe)|*.exe" };
            if (dlg.ShowDialog() == true) chosen = dlg.FileName;
        }
        else if (key == "fh3_extra")
        {
            var dlg = new Microsoft.Win32.OpenFolderDialog { Title = "Extra Forza Horizon 3 media folder (update / DLC tree with cars, db, stripped …)" };
            if (dlg.ShowDialog() != true) return;
            chosen = dlg.FolderName.TrimEnd('\\');
            // the folder above media is fine too
            if (!Directory.Exists(Path.Combine(chosen, "cars")) && Directory.Exists(Path.Combine(chosen, "media", "cars")))
                chosen = Path.Combine(chosen, "media");
            if (!Directory.Exists(Path.Combine(chosen, "cars")) && MessageBox.Show(
                    $"There is no cars folder in\n{chosen}\n\nUse this folder anyway?",
                    "FH2 Mod Studio", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                return;
        }
        else
        {
            var dlg = new Microsoft.Win32.OpenFolderDialog
            {
                Title = key == "game" ? "Forza Horizon 2 folder (the one that contains Mount)" : "Forza Horizon 3 installation folder (the one that contains media)"
            };
            if (dlg.ShowDialog() != true) return;
            chosen = dlg.FolderName;
            // accept the media / Mount folder itself too
            var name = Path.GetFileName(chosen.TrimEnd('\\'));
            if (key == "fh3" && name.Equals("media", StringComparison.OrdinalIgnoreCase)) chosen = Path.GetDirectoryName(chosen.TrimEnd('\\'))!;
            if (key == "game" && ModSettings.NormalizeGameRoot(chosen) is { } root)
            {
                chosen = root;   // Mount, media, the exe's folder or a folder above the game all lead here
                if (!ModSettings.IsGameRoot(_main.Settings.GameRoot)) { _main.Settings.GameRoot = root; _main.Settings.Save(); }
            }
            var probe = key == "game" ? Path.Combine(chosen, "Mount", "media", "stripped", "gamedbRC.slt")
                                      : Path.Combine(chosen, "media", "stripped", "gamedbRC.slt");
            if (!File.Exists(probe) && MessageBox.Show(
                    $"{(key == "game" ? "Forza Horizon 2" : "Forza Horizon 3")} was not found there:\n{probe} is missing.\n\nUse this folder anyway?",
                    "FH2 Mod Studio", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                return;
        }
        if (chosen == null) return;
        _porter.SetPath(key, chosen);
        _loaded = false;
        await CheckSetupAsync();
    }

    private async void ClearExtra_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _porter.Dir == null) return;
        _porter.SetPath("fh3_extra", "");
        _loaded = false;
        await CheckSetupAsync();
    }

    private void SetSetup(Brush dot, string title, string detail)
    {
        SetupDot.Fill = dot;
        SetupTitle.Text = title;
        SetupDetail.Text = detail;
    }

    private async void Recheck_Click(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        _loaded = false;
        await CheckSetupAsync();
    }

    private async void ChooseFolder_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new Microsoft.Win32.OpenFolderDialog { Title = "Folder that contains fh3port.py" };
        if (dlg.ShowDialog() != true) return;
        if (!File.Exists(Path.Combine(dlg.FolderName, "fh3port.py")))
        {
            MessageBox.Show("fh3port.py is not in that folder.", "FH2 Mod Studio", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }
        _porter.UseFolder(dlg.FolderName, _main.Settings);
        _main.Settings.Save();
        _loaded = false;
        await CheckSetupAsync();
    }

    // ───────────── choosing cars ─────────────

    private void Filter_Changed(object sender, EventArgs e) => ApplyFilter();

    private void ApplyFilter()
    {
        if (!IsInitialized || StatusFilter == null) return;
        var want = (StatusFilter.SelectedItem as ComboBoxItem)?.Tag as string ?? "new";
        var q = SearchBox.Text.Trim().ToLowerInvariant();
        var list = _cars
            .Where(c => want == "all" || c.Status == want)
            .Where(c => q.Length == 0 || (c.Title + " " + c.Media).ToLowerInvariant().Contains(q))
            .OrderBy(c => c.Make).ThenBy(c => c.Model).ThenBy(c => c.Year)
            .ToList();
        CarCombo.ItemsSource = list;
        CarComboCaption.Text = $"Car ({list.Count} matching)";
        if (list.Count == 1) CarCombo.SelectedIndex = 0;
        UpdateCarInfo();
    }

    private void CarCombo_SelectionChanged(object sender, SelectionChangedEventArgs e) => UpdateCarInfo();

    private void UpdateCarInfo()
    {
        var c = CarCombo.SelectedItem as Fh3Car;
        AddBtn.IsEnabled = c != null && !_chosen.Contains(c);
        CarInfo.Text = c == null ? "" :
            $"{c.Media}  ·  class {c.Class}  ·  {c.StatusText}" +
            (c.Status == "ported" ? "  -  converting again replaces the installed version" : "") +
            (c.Status == "in_fh2" ? "  -  FH2 has this car; the FH3 version (with FH3's body kits and parts) replaces it, FH2's is backed up and comes back with Undo" : "") +
            (c.Status == "failed" && c.Reason.Length > 0 ? "  -  last time: " + c.Reason : "");
    }

    private void Add_Click(object sender, RoutedEventArgs e)
    {
        if (CarCombo.SelectedItem is Fh3Car c && !_chosen.Contains(c)) _chosen.Add(c);
        UpdateCarInfo();
        UpdateRunState();
    }

    private void AddZip_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new Microsoft.Win32.OpenFileDialog
        {
            Title = "Forza Horizon 3 car zip(s) to convert",
            Filter = "Car zips (*.zip)|*.zip",
            Multiselect = true,
        };
        if (dlg.ShowDialog() != true) return;
        foreach (var path in dlg.FileNames)
        {
            var media = Path.GetFileNameWithoutExtension(path);
            // the database row is looked up by the zip's name (FH3's MediaName)
            var known = _cars.FirstOrDefault(c => c.Media.Equals(media, StringComparison.OrdinalIgnoreCase));
            var car = new Fh3Car
            {
                Media = known?.Media ?? media, Make = known?.Make ?? "", Model = known?.Model ?? media,
                YearRaw = known?.YearRaw ?? default, Class = known?.Class ?? "?", Status = known?.Status ?? "new",
                Replaces = known?.Replaces ?? "", ZipPath = path,
            };
            _chosen.Remove(_chosen.FirstOrDefault(c => c.Media.Equals(car.Media, StringComparison.OrdinalIgnoreCase))!);
            _chosen.Add(car);
            if (known == null)
                AppendLog($"{media}: not in the FH3 car list - the porter needs a Forza Horizon 3 database row named {media}; it reports it if there is none.");
        }
        UpdateCarInfo();
        UpdateRunState();
    }

    private void Remove_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is Fh3Car c) _chosen.Remove(c);
        UpdateCarInfo();
        UpdateRunState();
    }

    private void Clear_Click(object sender, RoutedEventArgs e)
    {
        _chosen.Clear();
        UpdateCarInfo();
        UpdateRunState();
    }

    private void Plates_Changed(object sender, RoutedEventArgs e)
    {
        if (_main == null) return;
        _main.Settings.PortKeepPlates = PlatesCheck.IsChecked == true;
        _main.Settings.Save();
    }

    private void UpdateRunState()
    {
        if (!IsInitialized) return;
        var gameRunning = _status.Game != GameState.NotRunning;
        ChosenCaption.Text = _chosen.Count == 0 ? "Cars to convert (none yet)" : $"Cars to convert ({_chosen.Count})";
        ConvertBtn.IsEnabled = _setupOk && !_busy && !gameRunning && _chosen.Count > 0;
        PortAllBtn.IsEnabled = _setupOk && !_busy && !gameRunning;
        UndoBtn.IsEnabled = !_busy && !gameRunning;
        RecheckBtn.IsEnabled = _setupOk && !_busy;
        NamesBtn.IsEnabled = _setupOk && !_busy && !gameRunning;
        RunHint.Text = _busy ? "Working…"
            : gameRunning ? "Close Forza Horizon 2 (Azimuth) first - the porter rewrites game files."
            : !_setupOk ? "The porter has to be ready first."
            : _chosen.Count == 0 ? "Add one or more cars above, or click \"Port all cars\"."
            : $"About 30-60 seconds per car. A snapshot is taken first, so the whole run can be undone.";
    }

    // ───────────── converting ─────────────

    private async void PortAll_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || !_setupOk) return;
        if (_status.Game != GameState.NotRunning)
        {
            MessageBox.Show("Close Forza Horizon 2 (Azimuth) first - the porter rewrites game files.",
                "Port all cars", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        var toPort = _cars.Where(c => !c.ReplacesFh2 && c.Status != "ported").ToList();
        if (toPort.Count == 0)
        {
            MessageBox.Show("All Forza Horizon 3 cars that are not in Forza Horizon 2 are already installed!",
                "Port all cars", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var count = toPort.Count;
        var summary = count <= 8
            ? string.Join("\n", toPort.Select(c => "  • " + c.Title))
            : string.Join("\n", toPort.Take(8).Select(c => "  • " + c.Title)) + $"\n  ... and {count - 8} more cars";

        if (MessageBox.Show(
                $"Convert and install all {count} FH3 cars that are not in Forza Horizon 2?\n\n{summary}\n\nLicence plates: {(PlatesCheck.IsChecked == true ? "imported" : "left out")}\n\nThe game database and car files are changed; a snapshot is taken first so you can undo it.",
                "Port all cars", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
            return;

        _chosen.Clear();
        foreach (var c in toPort) _chosen.Add(c);
        UpdateRunState();

        await ExecutePortAsync(toPort);
    }

    private async void Convert_Click(object sender, RoutedEventArgs e)
    {
        if (_chosen.Count == 0 || _busy) return;
        var count = _chosen.Count;
        var names = count <= 8
            ? string.Join("\n", _chosen.Select(c => "  • " + c.Title + (c.ReplacesFh2 ? "   (replaces FH2's version)" : "")))
            : string.Join("\n", _chosen.Take(8).Select(c => "  • " + c.Title + (c.ReplacesFh2 ? "   (replaces FH2's version)" : ""))) + $"\n  ... and {count - 8} more cars";

        if (MessageBox.Show(
                $"Convert and install these cars into Forza Horizon 2?\n\n{names}\n\nLicence plates: {(PlatesCheck.IsChecked == true ? "imported" : "left out")}\n\nThe game database and car files are changed; a snapshot is taken first so you can undo it.",
                "Convert FH3 cars", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
            return;

        await ExecutePortAsync(_chosen.ToList());
    }

    private async Task ExecutePortAsync(List<Fh3Car> cars)
    {
        var args = cars.Select(c => c.PortArg).ToList();
        if (PlatesCheck.IsChecked == true) args.Insert(0, "--keep-plates");
        StartRun($"Converting {cars.Count} car{(cars.Count == 1 ? "" : "s")}…");
        string? resultJson = null;
        int done = 0;
        try
        {
            var code = await _porter.RunAsync("batch_port.py", new[] { "port-cars" }.Concat(args), line =>
            {
                AppendLog(line);
                if (line.StartsWith("SNAPSHOT ")) _snapshot = line[9..].Trim();
                else if (line.StartsWith("RESULT ")) resultJson = line[7..];
                else if (line.StartsWith("   | == "))
                {
                    var media = line[8..].Split(' ')[0];
                    var car = cars.FirstOrDefault(c => c.Media.Equals(media, StringComparison.OrdinalIgnoreCase));
                    done++;
                    Dispatcher.BeginInvoke(() => ResultTitle.Text = $"Installing {car?.Title ?? media} ({Math.Min(done, cars.Count)} of {cars.Count})…");
                }
                else if (line.StartsWith("   | converting "))
                    Dispatcher.BeginInvoke(() => ResultTitle.Text = "Converting models, materials and textures…");
                else if (line.StartsWith("== batch ") && line.Contains("round 2"))
                    Dispatcher.BeginInvoke(() => ResultTitle.Text = "A car failed its checks - rolled back, converting the others again…");
            });
            ShowPortResult(code, resultJson, cars);
        }
        catch (Exception ex)
        {
            EndRun(Red, "The porter stopped: " + ex.Message);
        }
        await ReloadCarsAsync();
    }

    private void ShowPortResult(int code, string? json, List<Fh3Car> cars)
    {
        _results.Clear();
        if (json == null)
        {
            EndRun(Red, $"The porter stopped (exit code {code}) - see the log.");
            ShowLog(true);
            return;
        }
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        if (root.TryGetProperty("error", out var err))
        {
            EndRun(Red, err.GetString() ?? "error");
            return;
        }
        var ok = root.GetProperty("ok").EnumerateArray().Select(x => x.GetString() ?? "").ToHashSet(StringComparer.OrdinalIgnoreCase);
        var failed = root.GetProperty("failed").EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetString() ?? "", StringComparer.OrdinalIgnoreCase);
        foreach (var c in cars)
        {
            if (ok.Contains(c.Media))
                _results.Add(new PortResultRow { Glyph = "✓", Color = Green, Title = c.Title, Detail = $"{c.Media} - installed and checked" });
            else
                _results.Add(new PortResultRow { Glyph = "✗", Color = Red, Title = c.Title,
                    Detail = $"{c.Media} - not installed: {(failed.TryGetValue(c.Media, out var r) ? r : "see the log")}" });
        }
        foreach (var c in cars.Where(c => ok.Contains(c.Media)).ToList()) _chosen.Remove(c);
        UndoBtn.Visibility = _snapshot != null ? Visibility.Visible : Visibility.Collapsed;
        EndRun(failed.Count == 0 ? Green : ok.Count == 0 ? Red : Orange,
            failed.Count == 0 ? $"Done: {ok.Count} car{(ok.Count == 1 ? "" : "s")} installed. Start the game and find them in the Autoshow under their make."
                              : $"{ok.Count} installed, {failed.Count} failed (rolled back, nothing of them is left in the game).");
    }

    private async void Undo_Click(object sender, RoutedEventArgs e)
    {
        if (_snapshot == null || _busy) return;
        if (MessageBox.Show("Undo the last conversion?\n\nThe database and shared files go back to how they were before it, and the files it created are deleted.",
                "Undo conversion", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            return;
        StartRun("Undoing the last conversion…");
        _results.Clear();
        try
        {
            var code = await _porter.RunAsync("batch_port.py", new[] { "undo", _snapshot }, AppendLog);
            if (code == 0)
            {
                _snapshot = null;
                UndoBtn.Visibility = Visibility.Collapsed;
                EndRun(Green, "Undone - the game is back to how it was before that conversion.");
            }
            else EndRun(Red, $"Undo failed (exit code {code}) - see the log.");
        }
        catch (Exception ex)
        {
            EndRun(Red, "Undo failed: " + ex.Message);
        }
        await ReloadCarsAsync();
    }

    private async void RecheckCars_Click(object sender, RoutedEventArgs e)
    {
        var installed = _cars.Where(c => c.Status == "ported").ToList();
        if (installed.Count == 0 || _busy) return;
        StartRun($"Checking {installed.Count} installed cars…");
        _results.Clear();
        int bad = 0;
        try
        {
            await _porter.RunAsync("batch_port.py", new[] { "check" }.Concat(installed.Select(c => c.Media)), line =>
            {
                AppendLog(line);
                if (!line.StartsWith("CHECK ")) return;
                var parts = line[6..].Split(' ', 2);
                var media = parts[0];
                var rest = parts.Length > 1 ? parts[1] : "";
                var car = installed.FirstOrDefault(c => c.Media.Equals(media, StringComparison.OrdinalIgnoreCase));
                var good = rest.StartsWith("OK");
                if (!good) bad++;
                Dispatcher.BeginInvoke(() => _results.Add(new PortResultRow
                {
                    Glyph = good ? "✓" : "✗", Color = good ? Green : Red, Title = car?.Title ?? media,
                    Detail = good ? $"{media} - all checks passed" : $"{media} - {rest[4..].Trim()}"
                }));
            });
            EndRun(bad == 0 ? Green : Red, bad == 0 ? $"All {installed.Count} installed cars pass every check." : $"{bad} problem(s) found - see below.");
        }
        catch (Exception ex)
        {
            EndRun(Red, "Check failed: " + ex.Message);
        }
    }

    private async void Names_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _status.Game != GameState.NotRunning) return;
        StartRun("Writing car names into the string tables…");
        _results.Clear();
        try
        {
            string? summary = null;
            var code = await _porter.RunAsync("fh3port.py", new[] { "names" }, line =>
            {
                AppendLog(line);
                if (line.StartsWith("names: ")) summary = line[7..];
            });
            EndRun(code == 0 ? Green : Red, code == 0
                ? $"Car names written ({summary}). They show in the pause and race menus from the next game start."
                : $"Writing names failed (exit code {code}) - see the log.");
        }
        catch (Exception ex)
        {
            EndRun(Red, "Writing names failed: " + ex.Message);
        }
    }

    private async Task ReloadCarsAsync()
    {
        try
        {
            _cars = await _porter.LoadCarsAsync();
            var map = _cars.ToDictionary(c => c.Media, StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < _chosen.Count; i++)
                if (map.TryGetValue(_chosen[i].Media, out var fresh)) _chosen[i] = fresh;
            ApplyFilter();
        }
        catch { }
        UpdateRunState();
    }

    // ───────────── progress + log ─────────────

    private void StartRun(string title)
    {
        _busy = true;
        LogBox.Clear();
        ResultCaption.Visibility = Visibility.Visible;
        ResultCard.Visibility = Visibility.Visible;
        ResultDot.Fill = Orange;
        ResultTitle.Text = title;
        Progress.Visibility = Visibility.Visible;
        _logTimer.Start();
        _main.SetStatus(title);
        UpdateRunState();
    }

    private void EndRun(Brush dot, string title)
    {
        _busy = false;
        FlushLog();
        _logTimer.Stop();
        ResultDot.Fill = dot;
        ResultTitle.Text = title;
        Progress.Visibility = Visibility.Collapsed;
        _main.SetStatus(title);
        UpdateRunState();
    }

    private void AppendLog(string line)
    {
        lock (_pending) _pending.AppendLine(line);
    }

    private void FlushLog()
    {
        string text;
        lock (_pending)
        {
            if (_pending.Length == 0) return;
            text = _pending.ToString();
            _pending.Clear();
        }
        LogBox.AppendText(text);
        if (LogBox.Visibility == Visibility.Visible) LogBox.ScrollToEnd();
    }

    private void Log_Click(object sender, RoutedEventArgs e) => ShowLog(LogBox.Visibility != Visibility.Visible);

    private void ShowLog(bool show)
    {
        LogBox.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        LogBtn.Content = show ? "Hide log ▴" : "Show log ▾";
        if (show) LogBox.ScrollToEnd();
    }

    private void OpenFolder_Click(object sender, RoutedEventArgs e)
    {
        if (_porter.Dir != null) Process.Start(new ProcessStartInfo("explorer.exe", _porter.Dir) { UseShellExecute = true });
    }
}
