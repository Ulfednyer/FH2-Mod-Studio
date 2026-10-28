using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using FH2ModStudio.Core;
using Microsoft.Win32;

namespace FH2ModStudio.Views;

public partial class HomeView : UserControl
{
    private MainWindow _main = null!;
    private SessionStatus _status = new(GameState.NotRunning, false, false, 0, null);

    private static readonly SolidColorBrush DoneBg = new(Color.FromArgb(0x30, 0x34, 0xC7, 0x59));
    private static readonly SolidColorBrush DoneFg = new(Color.FromRgb(0x1E, 0x8E, 0x3E));
    private static readonly SolidColorBrush CurrentBg = new(Color.FromRgb(0x00, 0x7A, 0xFF));
    private static readonly SolidColorBrush TodoBg = new(Color.FromArgb(0x18, 0, 0, 0));
    private static readonly SolidColorBrush TodoFg = new(Color.FromRgb(0x8E, 0x8E, 0x93));

    public HomeView() => InitializeComponent();

    public void Init(MainWindow main)
    {
        _main = main;
        AzimuthBox.Text = main.Settings.AzimuthExe;
        GameBox.Text = main.Settings.GameRoot;
        AutoInjectCheck.IsChecked = main.Settings.AutoInject;
        RefreshPaths();
        RefreshSummary();
    }

    public void RefreshSummary()
    {
        var s = _main.Settings;
        var preset = RenderPatcher.Presets.FirstOrDefault(p => p.Id == s.Preset)?.Title ?? s.Preset;
        GraphicsSummary.Text =
            $"Quality: {preset}{(s.ShadowResolutionOverride > 0 || s.WindshieldResolutionOverride > 0 ? " (customized)" : "")}\n" +
            $"Draw distance: {s.DistanceFactor:0.#}×   ·   Anti-aliasing: {s.Msaa}x MSAA\n" +
            $"Motion blur reference: {s.MotionBlurFps} FPS";
        int enabled = s.DbMods.Count(m => m.Enabled);
        DbSummary.Text = s.DbMods.Count == 0
            ? "No saved database mods yet. Changes you make in the database are kept for this session; save them to re-apply on every launch."
            : $"{enabled} of {s.DbMods.Count} saved mod(s) enabled - applied automatically when the game's database is ready.";
    }

    public void OnStatus(SessionStatus s)
    {
        _status = s;
        bool running = s.Game != GameState.NotRunning;
        Step(Step1Circle, Step1Glyph, running ? 2 : 1, "1");
        Step(Step2Circle, Step2Glyph, s.ModsLoaded ? 2 : running ? 1 : 0, "2");
        Step(Step3Circle, Step3Glyph, s.Game == GameState.InGame ? 2 : s.ModsLoaded ? 1 : 0, "3");
        Step1Sub.Text = running ? $"Running (pid {s.Pid})" : "Not running";
        Step2Sub.Text = s.ModsLoaded ? "Active" : running ? (_main.Settings.AutoInject ? "Loading…" : "Waiting for you") : "-";
        Step3Sub.Text = s.Game == GameState.InGame ? (s.DatabaseReady ? "Database ready" : "Loading…") : "-";

        PrimaryBtn.Visibility = Visibility.Visible;
        PrimaryBtn.IsEnabled = true;
        if (!running)
        {
            GuidanceTxt.Text = _main.Settings.PathsValid
                ? "Ready. Launch Azimuth - mods load automatically, then start the game from the Azimuth launcher."
                : "Set the Azimuth and game locations under Setup first.";
            PrimaryBtn.Content = "Launch Azimuth";
            PrimaryBtn.IsEnabled = _main.Settings.PathsValid;
        }
        else if (!s.ModsLoaded)
        {
            GuidanceTxt.Text = s.Game == GameState.InGame
                ? "The game started without mods. Graphics and database edits work now; anti-aliasing applies next launch."
                : "Load the mods now, before starting the game in Azimuth.";
            PrimaryBtn.Content = "Load mods now";
        }
        else if (s.Game == GameState.Launcher)
        {
            GuidanceTxt.Text = "Mods are loaded. Start the game from the Azimuth launcher.";
            PrimaryBtn.Visibility = Visibility.Collapsed;
        }
        else
        {
            GuidanceTxt.Text = "All set - mods are active. Tweak graphics or edit the database while you play.";
            PrimaryBtn.Content = "Open database";
        }
    }

    private static void Step(Border circle, TextBlock glyph, int state, string number)
    {
        circle.Background = state == 2 ? DoneBg : state == 1 ? CurrentBg : TodoBg;
        glyph.Foreground = state == 2 ? DoneFg : state == 1 ? Brushes.White : TodoFg;
        glyph.Text = state == 2 ? "✓" : number;
    }

    private async void PrimaryBtn_Click(object sender, RoutedEventArgs e)
    {
        if (_status.Game == GameState.NotRunning)
        {
            var err = _main.Session.LaunchAzimuth();
            _main.SetStatus(err ?? "Starting Azimuth - mods will load automatically.");
        }
        else if (!_status.ModsLoaded)
        {
            var err = await Task.Run(() => _main.Session.InjectNow());
            _main.SetStatus(err ?? "Mods loaded.");
            await _main.Session.PollAsync();
        }
        else
        {
            _main.ShowPage("database");
        }
    }

    private void RefreshPaths()
    {
        var s = _main.Settings;
        Mark(AzimuthOk, File.Exists(s.AzimuthExe));
        Mark(GameOk, Directory.Exists(s.MediaDir));
    }

    private static void Mark(TextBlock t, bool ok)
    {
        t.Text = ok ? "✓" : "!";
        t.Foreground = ok ? DoneFg : new SolidColorBrush(Color.FromRgb(0xFF, 0x3B, 0x30));
        t.ToolTip = ok ? "Found" : "Not found";
    }

    private void Paths_LostFocus(object sender, RoutedEventArgs e)
    {
        _main.Settings.AzimuthExe = AzimuthBox.Text.Trim().Trim('"');
        _main.Settings.GameRoot = GameBox.Text.Trim().Trim('"');
        _main.Settings.Save();
        RefreshPaths();
        OnStatus(_status);
    }

    private void BrowseAzimuth_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new OpenFileDialog { Filter = "Azimuth|azimuth.exe|Programs|*.exe", Title = "Locate azimuth.exe" };
        if (dlg.ShowDialog() != true) return;
        AzimuthBox.Text = dlg.FileName;
        _main.Settings.AzimuthExe = dlg.FileName;
        _main.Settings.AutoDetectPaths();
        GameBox.Text = _main.Settings.GameRoot;
        Paths_LostFocus(sender, e);
    }

    private void BrowseGame_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new OpenFolderDialog { Title = "Select the Forza Horizon 2 folder (the one containing Mount)" };
        if (dlg.ShowDialog() != true) return;
        GameBox.Text = dlg.FolderName;
        Paths_LostFocus(sender, e);
    }

    private void AutoInject_Changed(object sender, RoutedEventArgs e)
    {
        if (_main == null) return;
        _main.Settings.AutoInject = AutoInjectCheck.IsChecked == true;
        _main.Settings.Save();
    }

    private void OpenGraphics_Click(object sender, RoutedEventArgs e) => _main.ShowPage("graphics");
    private void OpenDatabase_Click(object sender, RoutedEventArgs e) => _main.ShowPage("database");
}
