using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using FH2ModStudio.Core;

namespace FH2ModStudio.Views;

public partial class GraphicsView : UserControl
{
    private MainWindow _main = null!;
    private bool _loading = true;
    private bool _dirty;
    private SessionStatus _status = new(GameState.NotRunning, false, false, 0, null);
    private readonly Slider[] _blurSliders = new Slider[3];
    private readonly TextBlock[] _blurValues = new TextBlock[3];
    private readonly double[] _blur = new double[3];
    private int _gameFps;

    public GraphicsView() => InitializeComponent();

    public void Init(MainWindow main)
    {
        _main = main;
        var s = main.Settings;
        PresetList.ItemsSource = RenderPatcher.Presets;
        Fill(ShadowCombo, RenderPatcher.ResolutionOptions, v => v == 8192 ? "8192 × 8192 (experimental, heavy)" : $"{v} × {v}", true);
        Fill(WindshieldCombo, RenderPatcher.ResolutionOptions, v => v == 8192 ? "8192 × 8192 (experimental, heavy)" : $"{v} × {v}", true);
        _gameFps = s.AzimuthFrameRate();
        var fpsOptions = new[] { 30, 60, 120, 144, _gameFps }.Where(v => v > 0).Distinct().OrderBy(v => v);
        Fill(FpsCombo, fpsOptions, v => v == _gameFps ? $"{v} FPS - your frame rate (recommended)"
            : v == 60 ? "60 FPS - stock, long blur above 60 FPS" : v == 30 ? "30 FPS - very long blur" : $"{v} FPS");
        Fill(MsaaCombo, new[] { 1, 2, 4, 8 }, v => v == 1 ? "Off" : v == 4 ? "4x (game default)" : $"{v}x");
        BuildBlurRows();

        PresetList.SelectedItem = RenderPatcher.Presets.FirstOrDefault(p => p.Id == s.Preset) ?? RenderPatcher.Presets[0];
        Select(ShadowCombo, s.ShadowResolutionOverride);
        Select(WindshieldCombo, s.WindshieldResolutionOverride);
        Lod0Check.IsChecked = s.PlayerCarLod0;
        DistanceSlider.Value = s.DistanceFactor;
        Select(FpsCombo, s.MotionBlurFps);
        Select(MsaaCombo, s.Msaa);
        _blur[0] = s.BlurDriver; _blur[1] = s.BlurHood; _blur[2] = s.BlurBumper;
        for (int i = 0; i < 3; i++) ShowBlur(i);
        if (s.ShadowResolutionOverride > 0 || s.WindshieldResolutionOverride > 0) ToggleCustom(true);
        _loading = false;
        UpdateLabels();
        SetDirty(false);
    }

    public void OnShown() { }

    public void OnStatus(SessionStatus s) => _status = s;

    private static void Fill(ComboBox box, IEnumerable<int> values, Func<int, string> label, bool presetOption = false)
    {
        if (presetOption) box.Items.Add(new ComboBoxItem { Content = "Use preset", Tag = 0 });
        foreach (var v in values) box.Items.Add(new ComboBoxItem { Content = label(v), Tag = v });
    }

    private static void Select(ComboBox box, int value)
    {
        box.SelectedItem = box.Items.Cast<ComboBoxItem>().FirstOrDefault(i => (int)i.Tag == value) ?? box.Items[0];
    }

    private static int Selected(ComboBox box) => box.SelectedItem is ComboBoxItem { Tag: int v } ? v : 0;

    private void BuildBlurRows()
    {
        for (int i = 0; i < 3; i++)
        {
            int idx = i;
            var (camera, _, def) = LiveSettings.BlurGlobals[i];
            var label = new TextBlock { Text = camera, FontSize = 12, FontWeight = FontWeights.SemiBold, Foreground = (Brush)FindResource("TextPrimary"), VerticalAlignment = VerticalAlignment.Center };
            var slider = new Slider { Minimum = 0, Maximum = 1.5, TickFrequency = 0.05, IsSnapToTickEnabled = true, VerticalAlignment = VerticalAlignment.Center };
            var value = new TextBlock { FontSize = 12, Foreground = (Brush)FindResource("TextSecondary"), VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 0) };
            var reset = new Button { Content = "Default", Style = (Style)FindResource("GlassBtn"), Padding = new Thickness(10, 4, 10, 4) };
            slider.ValueChanged += (_, _) =>
            {
                if (_loading) return;
                _blur[idx] = Math.Round(slider.Value, 2);
                UpdateBlurText(idx);
                ApplyBlurLive(idx);
                SetDirty(true);
            };
            reset.Click += (_, _) =>
            {
                _blur[idx] = -1;
                ShowBlur(idx);
                ApplyBlurLive(idx);
                SetDirty(true);
            };
            Grid.SetRow(label, i); Grid.SetRow(slider, i); Grid.SetRow(value, i); Grid.SetRow(reset, i);
            Grid.SetColumn(slider, 1); Grid.SetColumn(value, 2); Grid.SetColumn(reset, 3);
            BlurGrid.Children.Add(label); BlurGrid.Children.Add(slider); BlurGrid.Children.Add(value); BlurGrid.Children.Add(reset);
            _blurSliders[i] = slider;
            _blurValues[i] = value;
        }
    }

    private void ShowBlur(int i)
    {
        bool was = _loading;
        _loading = true;
        _blurSliders[i].Value = _blur[i] < 0 ? LiveSettings.BlurGlobals[i].Default : _blur[i];
        _loading = was;
        UpdateBlurText(i);
    }

    private void UpdateBlurText(int i)
    {
        var def = LiveSettings.BlurGlobals[i].Default;
        _blurValues[i].Text = _blur[i] < 0 ? $"{def:0.##} (default)" : _blur[i] == 0 ? "Off" : $"{_blur[i]:0.##}";
    }

    private void ApplyBlurLive(int i)
    {
        var game = _main.Session.Game;
        if (game == null || _status.Game != GameState.InGame) return;
        float v = (float)(_blur[i] < 0 ? LiveSettings.BlurGlobals[i].Default : _blur[i]);
        if (LiveSettings.WriteBlur(game, i, v))
            _main.SetStatus($"{LiveSettings.BlurGlobals[i].Camera} motion blur set to {v:0.##} in game.");
    }

    private void Any_Changed(object sender, RoutedEventArgs e)
    {
        if (_loading) return;
        UpdateLabels();
        SetDirty(true);
    }

    private void PresetList_SelectionChanged(object sender, SelectionChangedEventArgs e) => Any_Changed(sender, e);

    private void UpdateLabels()
    {
        DistanceTxt.Text = DistanceSlider.Value.ToString("0.#", CultureInfo.InvariantCulture) + "×";
        int fps = Selected(FpsCombo);
        FpsWarning.Visibility = _gameFps > 0 && fps > 0 && fps < _gameFps * 0.8 ? Visibility.Visible : Visibility.Collapsed;
        FpsWarning.Text = $"⚠ Below your frame rate of {_gameFps} FPS - motion blur will look stretched and smeared.";
        int launchMsaa = _status.Game == GameState.InGame && _main.Session.Game is { } g ? LiveSettings.ReadMsaa(g) ?? 0 : 0;
        MsaaInfo.Text = "Smooths jagged edges. Set when the game starts, so restart Azimuth after changing it." +
                        (launchMsaa > 0 ? $"  Running now: {launchMsaa}x." : "");
    }

    private void SetDirty(bool dirty)
    {
        _dirty = dirty;
        var c = dirty ? Color.FromRgb(0xFF, 0x95, 0x00) : Color.FromRgb(0x34, 0xC7, 0x59);
        DirtyDot.Fill = new SolidColorBrush(c);
        DirtyTxt.Foreground = new SolidColorBrush(dirty ? Color.FromRgb(0xC9, 0x6F, 0x00) : Color.FromRgb(0x1E, 0x8E, 0x3E));
        DirtyTxt.Text = dirty ? "Unsaved changes - press Apply to keep them" : "All changes applied";
        ApplyBtn.IsEnabled = dirty;
    }

    private void Customize_Click(object sender, RoutedEventArgs e) => ToggleCustom(CustomPanel.Visibility != Visibility.Visible);

    private void ToggleCustom(bool show)
    {
        CustomPanel.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        CustomizeBtn.Content = show ? "Customize ▴" : "Customize ▾";
    }

    private void Apply_Click(object sender, RoutedEventArgs e)
    {
        var s = _main.Settings;
        var before = (s.Preset, s.ShadowResolutionOverride, s.WindshieldResolutionOverride, s.PlayerCarLod0, s.DistanceFactor, s.MotionBlurFps);
        int msaaBefore = s.Msaa;
        s.Preset = (PresetList.SelectedItem as PresetInfo)?.Id ?? "stock";
        s.ShadowResolutionOverride = Selected(ShadowCombo);
        s.WindshieldResolutionOverride = Selected(WindshieldCombo);
        s.PlayerCarLod0 = Lod0Check.IsChecked == true;
        s.DistanceFactor = DistanceSlider.Value;
        s.MotionBlurFps = Selected(FpsCombo);
        s.Msaa = Selected(MsaaCombo);
        s.BlurDriver = _blur[0]; s.BlurHood = _blur[1]; s.BlurBumper = _blur[2];
        try
        {
            if (!Directory.Exists(s.MediaDir)) throw new IOException("Game folder not found - check Setup on the Home page.");
            RenderPatcher.Apply(s);
            s.WriteDllIni();
            s.Save();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _main.SetStatus("Could not apply: " + ex.Message);
            return;
        }
        var after = (s.Preset, s.ShadowResolutionOverride, s.WindshieldResolutionOverride, s.PlayerCarLod0, s.DistanceFactor, s.MotionBlurFps);
        var notes = new List<string> { "Applied." };
        bool running = _status.Game != GameState.NotRunning;
        if (running && before != after) notes.Add("Restart the game to see quality / distance / blur-FPS changes.");
        if (running && msaaBefore != s.Msaa) notes.Add("Restart Azimuth for the new anti-aliasing.");
        if (!running) notes.Add("Everything takes effect when you launch the game.");
        _main.SetStatus(string.Join(" ", notes));
        SetDirty(false);
        _main.HomePage.RefreshSummary();
    }

    private void RestoreStock_Click(object sender, RoutedEventArgs e)
    {
        var s = _main.Settings;
        if (MessageBox.Show("Put the game's original graphics files back?\n\nYour motion blur frame rate is kept, because the stock value makes motion blur far too long at high frame rates. " +
                "Your other choices on this page are kept too - press Apply later to use them again.",
                "Restore stock graphics", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        try
        {
            RenderPatcher.RestoreStock(s);
            _main.SetStatus("Original graphics files restored. Restart the game to see them.");
            SetDirty(true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _main.SetStatus("Could not restore: " + ex.Message);
        }
    }

    private async void ReadLive_Click(object sender, RoutedEventArgs e)
    {
        var game = _main.Session.Game;
        if (game == null || _status.Game != GameState.InGame)
        {
            _main.SetStatus("Start the game and drive into the world first.");
            return;
        }
        ReadLiveBtn.IsEnabled = false;
        LiveProgress.Visibility = Visibility.Visible;
        _main.SetStatus(_main.Session.Live.HasScan(game) ? "Reading live values…" : "Searching game memory (about a minute)…");
        var rows = await Task.Run(() =>
        {
            var live = _main.Session.Live;
            if (!live.HasScan(game)) live.Scan(game);
            var list = LiveSettings.Fields.Select(f =>
            {
                var v = live.Read(game, f);
                var text = v == null ? "not found" : v.Value.ToString("0.###", CultureInfo.InvariantCulture);
                return new { Label = f.Label, Value = f.VisibleEffect ? text : text + "   (no visible effect in testing)" };
            }).ToList();
            for (int i = 0; i < 3; i++)
                list.Add(new { Label = "Motion blur: " + LiveSettings.BlurGlobals[i].Camera, Value = LiveSettings.ReadBlur(game, i)?.ToString("0.##") ?? "-" });
            list.Add(new { Label = "MSAA samples", Value = LiveSettings.ReadMsaa(game)?.ToString() ?? "-" });
            return list;
        });
        LiveList.ItemsSource = rows;
        LiveProgress.Visibility = Visibility.Collapsed;
        ReadLiveBtn.IsEnabled = true;
        _main.SetStatus("Live values read from the game.");
    }
}
