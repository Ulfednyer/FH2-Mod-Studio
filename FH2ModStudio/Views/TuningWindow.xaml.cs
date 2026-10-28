using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using FH2ModStudio.Core;

namespace FH2ModStudio.Views;

/// <summary>
/// Drift suspension values (alignment rows + fh2sql.dll steering) and the tuning menu's slider ranges
/// (PhysicsSettings.ini [CarTuning]); both saved for the next game start and, while the game runs, changed live.
/// </summary>
public partial class TuningWindow : Window
{
    private readonly MainWindow _main;
    private readonly Func<ICarDb> _db;
    private readonly Dictionary<string, TextBox> _limitBoxes = new();
    private readonly Dictionary<string, TextBox> _driftBoxes = new();
    private Dictionary<string, double> _stock = new();

    private static readonly (string Key, string Label, string Hint, double Default)[] DriftFields =
    {
        ("DriftFrontCamber", "Front camber (°)", "FM7 drift: -3 · default -5", -5.0),
        ("DriftRearCamber", "Rear camber (°)", "default -1", -1.0),
        ("DriftRearToe", "Rear toe (°)", "negative = toe-out · default -0.05", -0.05),
        ("DriftSteerLock", "Steering lock (°)", "FM7 drift: 60 · 0 = the car's own", 60.0),
        ("DriftSteerSpeed", "Steering speed (×)", "FM7 drift: 1.5", 1.5),
    };

    public TuningWindow(MainWindow main, Func<ICarDb> db)
    {
        InitializeComponent();
        _main = main;
        _db = db;
        BuildDrift();
        BuildLimits();
        Load();
    }

    private GameProcess? LiveGame =>
        _main.Session.Status.Game == GameState.InGame && _main.Session.Game is { HasExited: false } g ? g : null;

    private static TextBox Box() => new() { Style = (Style)Application.Current.FindResource("GlassTextBox"), Margin = new Thickness(0, 2, 8, 2), FontSize = 12 };

    private static TextBlock Text(string s, bool bold = false, Brush? color = null) => new()
    {
        Text = s, FontSize = 12, VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap,
        FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal, Foreground = color ?? new SolidColorBrush(Color.FromRgb(0x1C, 0x1C, 0x1E)),
    };

    private static void Place(Grid g, UIElement e, int row, int col)
    {
        while (g.RowDefinitions.Count <= row) g.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        Grid.SetRow(e, row);
        Grid.SetColumn(e, col);
        g.Children.Add(e);
    }

    private void BuildDrift()
    {
        int r = 0;
        foreach (var (key, label, hint, _) in DriftFields)
        {
            var box = Box();
            _driftBoxes[key] = box;
            Place(DriftGrid, Text(label), r, 0);
            Place(DriftGrid, box, r, 1);
            Place(DriftGrid, Text(hint, color: Brushes.Gray), r++, 2);
        }
    }

    private void BuildLimits()
    {
        int r = 0;
        Place(LimitsGrid, Text("Setting", true), r, 0);
        Place(LimitsGrid, Text("Min", true), r, 1);
        Place(LimitsGrid, Text("Max", true), r, 2);
        Place(LimitsGrid, Text("Stock", true), r++, 3);
        foreach (var group in TuningLimits.Fields.GroupBy(f => f.Label))
        {
            Place(LimitsGrid, Text(group.Key), r, 0);
            foreach (var f in group)
            {
                var box = Box();
                box.Tag = f.Key;
                _limitBoxes[f.Key] = box;
                // TuneLSDTorqueMaxDecel is a single maximum: shown in the Max column
                Place(LimitsGrid, box, r, f.Key.EndsWith("Min") ? 1 : 2);
            }
            var stockTxt = Text("", color: Brushes.Gray);
            stockTxt.Tag = group.Select(f => f.Key).ToArray();
            Place(LimitsGrid, stockTxt, r++, 3);
        }
    }

    private static string F(double v) => v.ToString("0.####", CultureInfo.InvariantCulture);

    private void Load()
    {
        var s = _main.Settings;
        foreach (var (key, _, _, _) in DriftFields)
            _driftBoxes[key].Text = F((double)typeof(ModSettings).GetProperty(key)!.GetValue(s)!);

        _stock = TuningLimits.ReadStock(s);
        var game = LiveGame;
        var values = (game != null ? TuningLimits.ReadLive(game) : null) ?? TuningLimits.ReadFile(TuningLimits.IniPath(s));
        foreach (var (key, box) in _limitBoxes)
            box.Text = values.TryGetValue(key, out var v) ? F(v) : "";
        foreach (var t in LimitsGrid.Children.OfType<TextBlock>().Where(t => t.Tag is string[]))
            t.Text = string.Join("  …  ", ((string[])t.Tag).Select(k => _stock.TryGetValue(k, out var v) ? F(v) : "-"));

        bool live = game != null && TuningLimits.LiveObject(game) != null;
        ModeTxt.Text = live ? "Game running - changes apply live" : "Game not running - saved for the next start";
        ModeTxt.Foreground = new SolidColorBrush(live ? Color.FromRgb(0x1E, 0x8E, 0x3E) : Color.FromRgb(0x63, 0x63, 0x66));
        ModeBadge.Background = new SolidColorBrush(live ? Color.FromArgb(0x20, 0x34, 0xC7, 0x59) : Color.FromArgb(0x14, 0, 0, 0));
        ModeBadge.BorderBrush = new SolidColorBrush(live ? Color.FromArgb(0x60, 0x34, 0xC7, 0x59) : Color.FromArgb(0x30, 0, 0, 0));
        var file = TuningLimits.ReadFile(TuningLimits.IniPath(s));
        bool changed = _stock.Any(kv => !file.TryGetValue(kv.Key, out var v) || Math.Abs(v - kv.Value) > 1e-6);
        StatusTxt.Text = changed ? "Tuning ranges differ from the game's - \"Restore stock\" brings them back." : "";
    }

    private static readonly Brush NormalBorder = new SolidColorBrush(Color.FromArgb(0x80, 0xAA, 0xAA, 0xAA));   // GlassTextBox

    private bool TryParse(TextBox box, out double v)
    {
        bool ok = double.TryParse(box.Text.Trim().Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out v);
        box.BorderBrush = ok ? NormalBorder : Brushes.Red;
        return ok;
    }

    private async void Apply_Click(object sender, RoutedEventArgs e)
    {
        var s = _main.Settings;
        var drift = new Dictionary<string, double>();
        var limits = new Dictionary<string, double>();
        bool ok = true;
        foreach (var (key, box) in _driftBoxes) ok &= TryParse(box, out var v) && drift.TryAdd(key, v);
        foreach (var (key, box) in _limitBoxes)
            if (box.Text.Trim().Length > 0) ok &= TryParse(box, out var v) && limits.TryAdd(key, v);
        foreach (var f in TuningLimits.Fields.Where(f => f.Key.EndsWith("Min")))
        {
            var max = f.Key[..^3] + "Max";
            if (limits.TryGetValue(f.Key, out var lo) && limits.TryGetValue(max, out var hi) && lo >= hi)
            {
                _limitBoxes[f.Key].BorderBrush = Brushes.Red;
                ok = false;
            }
        }
        if (!ok)
        {
            StatusTxt.Text = "Fix the values marked red (numbers; every minimum below its maximum).";
            return;
        }

        foreach (var (key, v) in drift) typeof(ModSettings).GetProperty(key)!.SetValue(s, v);
        var game = LiveGame;
        var msgs = new List<string>();
        var err = await Task.Run(() =>
        {
            // drift: saved mod + its alignment rows in the current database, steering in fh2sql.ini (+ live via the DLL)
            string? e2 = null;
            if (DriftDragPack.IsSaved(s))
            {
                DriftDragPack.UpdateSaved(s);
                e2 = _db().Execute(DriftDragPack.AlignmentSql(s), "Drift suspension alignment");
            }
            s.Save();
            s.WriteDllIni();
            if (game != null) e2 ??= DriftDragPack.SendSteering(_main.Session.Sql, s);
            // tuning ranges: the file always, the running game too
            try
            {
                TuningLimits.WriteFile(s, limits);
            }
            catch (IOException ex)
            {
                e2 ??= "PhysicsSettings.ini: " + ex.Message;
            }
            if (game != null)
            {
                int n = TuningLimits.WriteLive(game, limits);
                msgs.Add(n < 0 ? "tuning ranges not found in the running game (saved for the next start)" : $"{n} tuning ranges changed live");
            }
            return e2;
        });
        if (!DriftDragPack.IsSaved(s)) msgs.Add("drift values saved - add the drift parts with the button in the car list to use them");
        StatusTxt.Text = err != null ? "Error: " + err
            : "Saved" + (game != null ? " and applied to the running game (re-select the car, reopen the tuning menu)" : " - the game uses them on its next start") +
              (msgs.Count > 0 ? ". " + string.Join("; ", msgs) + "." : ".");
        _main.SetStatus(StatusTxt.Text);
    }

    private void Stock_Click(object sender, RoutedEventArgs e)
    {
        foreach (var (key, _, _, def) in DriftFields) _driftBoxes[key].Text = F(def);
        foreach (var (key, box) in _limitBoxes)
            if (_stock.TryGetValue(key, out var v)) box.Text = F(v);
        StatusTxt.Text = "Stock values filled in - Apply to use them.";
    }

    private void TitleBar_MouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton == MouseButton.Left) DragMove();
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) => Close();
}
