using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using FH2ModStudio.Core;

namespace FH2ModStudio.Views;

public sealed class SectionItem
{
    public SectionDef Def { get; init; } = null!;
    public string Title => Def.Title;
    public string Badge { get; set; } = "";
}

internal sealed class PendingEdit
{
    public string Table = "", KeyColumn = "", Key = "", Column = "";
    public string? Current, Stock, Value;
    public bool Valid = true;
}

internal sealed class GroupData
{
    public GroupDef Def = null!;
    public string? Where;
    public List<string> Tables = new();
    public string? Table;
    public SqlResult? Current;
    public Dictionary<string, List<string?>> Stock = new();
    public List<string> StockColumns = new();
    public List<(string Key, string Label)> Rows = new();
    public string? SelectedKey;
    public string? Shared;
    public Dictionary<string, string> RefLabels = new();
}

public partial class CarsView : UserControl
{
    private static readonly SolidColorBrush PendingBrush = new(Color.FromRgb(0xFF, 0x95, 0x00));
    private static readonly SolidColorBrush ModdedBrush = new(Color.FromRgb(0x00, 0x7A, 0xFF));
    private static readonly SolidColorBrush ErrorBrush = new(Color.FromRgb(0xFF, 0x3B, 0x30));
    private static readonly SolidColorBrush NormalBorder = new(Color.FromArgb(0x80, 0xAA, 0xAA, 0xAA));

    private MainWindow _main = null!;
    private SessionStatus _status = new(GameState.NotRunning, false, false, 0, null);
    private SqliteCarDb? _stock;
    private SqliteCarDb? _offline;
    private string _offlineModsHash = "";
    private LiveCarDb _live = null!;
    private Dictionary<string, List<(string Value, string Label)>> _options = new();
    private List<CarEntry> _catalog = new();
    private CarEntry? _car;
    private CarIds? _ids;
    private ICarDb? _db;
    private readonly Dictionary<string, PendingEdit> _pending = new();
    private List<SectionItem> _sections = new();
    private int _loadToken;

    public CarsView() => InitializeComponent();

    public void Init(MainWindow main)
    {
        _main = main;
        DriftDragPack.UpdateSaved(main.Settings);   // an older saved drift/drag mod -> current version before the game gets it
        _live = new LiveCarDb(main.Session);
        _sections = CarModel.Sections.Select(s => new SectionItem { Def = s }).ToList();
        SectionList.ItemsSource = _sections;
        UpdateDirty();
    }

    public async void OnShown()
    {
        if (_stock != null) return;
        var path = Path.Combine(_main.Settings.MediaDir, "stripped", "gamedbRC.slt");
        if (!File.Exists(path))
        {
            EmptyTxt.Text = "The game database (media\\stripped\\gamedbRC.slt) was not found. Check the game folder under Setup on the Home page.";
            return;
        }
        CarCountTxt.Text = "loading…";
        var carsDir = Path.Combine(_main.Settings.MediaDir, "cars");
        (_stock, _catalog, _options) = await Task.Run(() =>
        {
            var stock = SqliteCarDb.OpenStock(path);
            return (stock, CarModel.LoadCatalog(stock, carsDir), CarModel.LoadOptions(stock));
        });
        CarCountTxt.Text = _catalog.Count.ToString(CultureInfo.InvariantCulture);
        ApplySearch();
    }

    public void OnStatus(SessionStatus s)
    {
        bool modeChanged = s.DatabaseReady != _status.DatabaseReady;
        _status = s;
        if (modeChanged && _car != null && _pending.Count == 0) _ = LoadCarAsync(_car);
        else UpdateModeBadge();
    }

    // ───────────── car list ─────────────

    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        SearchHint.Visibility = SearchBox.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        ApplySearch();
    }

    private void ApplySearch()
    {
        var terms = SearchBox.Text.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        CarList.ItemsSource = terms.Length == 0
            ? _catalog
            : _catalog.Where(c => terms.All(t => c.Media.Contains(t, StringComparison.OrdinalIgnoreCase) ||
                                               c.Subtitle.Contains(t, StringComparison.OrdinalIgnoreCase))).ToList();
    }

    private void CarList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (CarList.SelectedItem is not CarEntry car || car == _car) return;
        if (_pending.Count > 0 && MessageBox.Show($"You have {_pending.Count} unapplied change(s) on {_car?.Media}. Discard them and open {car.Media}?",
                "Unapplied changes", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK)
        {
            CarList.SelectedItem = _car;
            return;
        }
        _pending.Clear();
        _ = LoadCarAsync(car);
    }

    private ICarDb CurrentDb()
    {
        if (_status.DatabaseReady) return _live;
        var hash = string.Join("|", _main.Settings.DbMods.Where(m => m.Enabled).Select(m => m.Sql.GetHashCode()));
        if (_offline == null || hash != _offlineModsHash)
        {
            _offline?.Dispose();
            _offline = SqliteCarDb.CreateWorkingCopy(_stock!, _main.Settings.DbMods);
            _offlineModsHash = hash;
        }
        return _offline;
    }

    private async Task LoadCarAsync(CarEntry car)
    {
        _car = car;
        EmptyPanel.Visibility = Visibility.Collapsed;
        HeaderCard.Visibility = EditorArea.Visibility = ApplyBar.Visibility = Visibility.Visible;
        CarTitle.Text = car.Media;
        CarSubtitle.Text = car.Subtitle;
        LoadProgress.Visibility = Visibility.Visible;
        var (db, ids, facts) = await Task.Run(() =>
        {
            var d = CurrentDb();
            var i = CarModel.ResolveIds(d, car);
            var f = d.Query($"SELECT DriveTypeID, AspirationTypeId, EngineConfigID, CurbWeight, GameTorqueScale, NumGears, FrontTireWidthMM, RearTireWidthMM FROM Data_Car WHERE Id = {car.Id};", out _);
            return (d, i, f);
        });
        if (_car != car) return;
        _db = db;
        _ids = ids;
        BuildChips(facts);
        UpdateModeBadge();
        UpdateModifiedText();
        if (SectionList.SelectedIndex < 0) SectionList.SelectedIndex = 0;
        else await LoadSectionAsync();
    }

    private void BuildChips(SqlResult? facts)
    {
        ChipPanel.Children.Clear();
        if (facts is not { Rows.Count: > 0 }) return;
        var r = facts.Rows[0];
        string Opt(string col, string? v) => _options.TryGetValue(col, out var o) ? o.FirstOrDefault(x => x.Value == v).Label ?? v ?? "-" : v ?? "-";
        var engineMenu = new[] { ("Add turbo or supercharger…", UpgradeKind.Aspiration, (string?)null), ("Swap engine…", UpgradeKind.EngineSwap, null), ("Add a level to an engine part…", UpgradeKind.ExtraLevel, "List_UpgradeEngineCamshaft") };
        var tyreMenu = new[] { ("Add tyre compound…", UpgradeKind.TireCompound, (string?)null), ("Add wider tyres…", UpgradeKind.TireWidth, null), ("Set wheel spacers…", UpgradeKind.Spacers, null) };
        AddChip(Opt("DriveTypeID", r[0]), menu: new[] { ("Convert drivetrain (FWD / RWD / AWD)…", UpgradeKind.DrivetrainSwap, (string?)null) });
        AddChip(Opt("AspirationTypeId", r[1]), menu: engineMenu);
        AddChip(Opt("EngineConfigID", r[2]) + " engine", menu: engineMenu);
        AddChip($"{r[5]} gears", menu: new[] { ("Add a gearbox level…", UpgradeKind.ExtraLevel, (string?)"List_UpgradeDrivetrainTransmission") });
        AddChip($"{r[6]}/{r[7]} tyres", menu: tyreMenu);
        AddChip($"Weight {r[3]}", menu: new[] { ("Add a weight-reduction level…", UpgradeKind.ExtraLevel, (string?)"List_UpgradeCarBodyWeight") });
        AddChip($"Torque ×{r[4]}", menu: engineMenu);
        if (_ids?.EngineShare > 1) AddChip($"Engine shared by {_ids.EngineShare} cars", true);
    }

    private void AddChip(string text, bool warn = false, (string Label, UpgradeKind Kind, string? Table)[]? menu = null)
    {
        var chip = new Border
        {
            CornerRadius = new CornerRadius(9), Padding = new Thickness(9, 3, 9, 3), Margin = new Thickness(0, 0, 6, 4), BorderThickness = new Thickness(1),
            Background = new SolidColorBrush(warn ? Color.FromArgb(0x20, 0xFF, 0x95, 0x00) : Color.FromArgb(0x14, 0, 0, 0)),
            BorderBrush = new SolidColorBrush(warn ? Color.FromArgb(0x60, 0xFF, 0x95, 0x00) : Color.FromArgb(0x20, 0, 0, 0)),
            Child = new TextBlock { Text = text, FontSize = 11, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(warn ? Color.FromRgb(0xC9, 0x6F, 0x00) : Color.FromRgb(0x48, 0x48, 0x4A)) },
        };
        if (menu != null)
        {
            var cm = new ContextMenu();
            foreach (var (label, kind, table) in menu)
            {
                var item = new MenuItem { Header = label };
                item.Click += (_, _) => OpenAddDialog(kind, table);
                cm.Items.Add(item);
            }
            var all = new MenuItem { Header = "Add another upgrade…" };
            all.Click += (_, _) => OpenAddDialog(menu[0].Kind, null);
            cm.Items.Add(all);
            chip.ContextMenu = cm;
            chip.ToolTip = "Right-click for upgrade options";
        }
        ChipPanel.Children.Add(chip);
    }

    // ───────────── adding / removing upgrades ─────────────

    private static string SectionFor(UpgradeKind kind) => kind switch
    {
        UpgradeKind.Aspiration or UpgradeKind.EngineSwap => "engine",
        UpgradeKind.DrivetrainSwap => "drivetrain",
        UpgradeKind.TireCompound or UpgradeKind.TireWidth or UpgradeKind.Spacers => "tires",
        _ => "",
    };

    private void AddUpgrade_Click(object sender, RoutedEventArgs e) => OpenAddDialog(UpgradeKind.Aspiration, null);

    private async void DriftDrag_Click(object sender, RoutedEventArgs e)
    {
        if (_stock == null) return;
        var s = _main.Settings;
        var before = await Task.Run(() => DriftDragPack.Count(CurrentDb()));
        var saved = DriftDragPack.IsSaved(s);
        if (saved && before.Drag >= before.Cars && before.Drift >= before.Cars && before.DriftTyres > 0)
        {
            var textErr = _status.DatabaseReady ? null : await DriftDragPack.WriteShopTextsAsync(s);
            _main.SetStatus($"All {before.Cars} cars already have drift suspension, drift tyres and drag tyres." +
                            (textErr != null ? " Shop names not written: " + textErr : "") + " Values: \"Drift setup & tuning ranges…\".");
            return;
        }
        if (MessageBox.Show(
                $"Add three upgrades to every car ({before.Cars}):\n\n" +
                FormattableString.Invariant($"  • Drift suspension (suspension level 5) - the car's race springs with a drift alignment (front camber {s.DriftFrontCamber:0.##}°, rear {s.DriftRearCamber:0.##}°, rear toe {s.DriftRearToe:0.##}°) and, like ") +
                FormattableString.Invariant($"Forza Motorsport 7, {s.DriftSteerLock:0}° steering lock with faster steering while it is installed (needs the game started from FH2 Mod Studio), 2,050 CR\n") +
                "  • Drift tyres (tyre level 6) - Forza Horizon 3's drift compound: less grip, long predictable slides, 8,000 CR\n" +
                "  • Drag tyres (tyre level 4) - Forza Horizon 3's drag compound on the drag tyre model, 10,000 CR\n\n" +
                "They appear in the upgrade shop. The values can be changed any time under \"Drift setup & tuning ranges…\". " +
                "It is saved as a mod, so the game gets them on every start (remove it in the Database tab).",
                "Drift & drag parts", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK)
            return;
        DriftDragBtn.IsEnabled = false;
        var (error, after, live) = await Task.Run(() =>
        {
            var db = CurrentDb();
            var err = DriftDragPack.Apply(db, s);
            if (err == null)
            {
                DriftDragPack.Save(s);
                if (!db.IsLive) _offlineModsHash = string.Join("|", s.DbMods.Where(m => m.Enabled).Select(m => m.Sql.GetHashCode()));
                else DriftDragPack.SendSteering(_main.Session.Sql, s);
            }
            return (err, DriftDragPack.Count(db), db.IsLive);
        });
        if (error != null)
        {
            DriftDragBtn.IsEnabled = true;
            _main.SetStatus("Could not add the drift and drag parts: " + error);
            return;
        }
        // shop names of the new levels; string tables can only change while the game is closed
        var textError = live ? "the game is running - click this button again after closing it" : await DriftDragPack.WriteShopTextsAsync(s);
        DriftDragBtn.IsEnabled = true;
        _main.SetStatus($"Drift suspension on {after.Drift}, drift tyres on {after.DriftTyres} and drag tyres on {after.Drag} of {after.Cars} cars. " +
                        (live ? "Re-select a car, then open the upgrade shop." : "The game gets them on its next start.") +
                        (textError != null ? " Shop names not written yet: " + textError + "." : ""));
        _main.HomePage.RefreshSummary();
        if (_car != null) await LoadCarAsync(_car);
    }

    private void DriftSetup_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new TuningWindow(_main, CurrentDb) { Owner = Window.GetWindow(this) };
        dlg.ShowDialog();
        if (!_status.DatabaseReady) _offlineModsHash = "";   // the offline copy is rebuilt with the updated mod
        if (_car != null) _ = LoadCarAsync(_car);
    }

    private async void OpenAddDialog(UpgradeKind kind, string? table)
    {
        if (_car == null || _ids == null || _stock == null) return;
        var car = _car;
        var ids = _ids;
        var db = await Task.Run(CurrentDb);
        var dlg = new AddUpgradeWindow(db, _stock, ids, kind, table) { Owner = Window.GetWindow(this) };
        if (dlg.ShowDialog() != true || dlg.ResultSql == null) return;
        bool keep = !_status.DatabaseReady || KeepCheck.IsChecked == true;
        var sql = dlg.ResultSql;
        var desc = $"{car.Media}: {dlg.ResultDescription}";
        var error = await Task.Run(() =>
        {
            var err = db.Execute(sql, desc);
            if (err == null && keep) CarModel.UpsertCarMod(_main.Settings, car.Media, CarModel.DiffAgainstStock(db, _stock, ids));
            if (!db.IsLive) _offlineModsHash = string.Join("|", _main.Settings.DbMods.Where(m => m.Enabled).Select(m => m.Sql.GetHashCode()));
            return err;
        });
        if (error != null)
        {
            _main.SetStatus("Could not add the upgrade: " + error);
            return;
        }
        _main.SetStatus($"{dlg.ResultDescription} on {car.Media} - shown under {dlg.ResultWhere}.{(keep ? " Kept for future launches." : "")} " +
                        "Re-select the car, then open the upgrade shop.");
        _main.HomePage.RefreshSummary();
        UpdateModifiedText();
        var target = SectionFor(kind);
        if (target.Length > 0) SectionList.SelectedItem = _sections.First(s => s.Def.Id == target);
        await LoadCarAsync(car);
    }

    private async void RemoveAdded(string table, string keyColumn, string key, string label)
    {
        if (_car == null || _ids == null || _stock == null) return;
        var question = table == "List_UpgradeCarBody"
            ? $"Remove the shop spacer upgrade ({label})?\n\nIf it is fitted to a car in your garage, switch that car back to the stock body in the upgrade shop first - otherwise the game looks for a part that no longer exists."
            : $"Remove the upgrade you added ({label})?";
        if (MessageBox.Show(question, "Remove upgrade", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        var car = _car;
        var ids = _ids;
        bool keep = !_status.DatabaseReady || KeepCheck.IsChecked == true;
        var error = await Task.Run(() =>
        {
            var db = CurrentDb();
            var sql = Upgrades.RemovalExtras(db, table, key) +
                      $"DELETE FROM {DbHistory.QuoteIdent(table)} WHERE {DbHistory.QuoteIdent(keyColumn)} = {DbHistory.Literal(key)};";
            var err = db.Execute(sql, $"{car.Media}: removed {label}");
            if (err == null && keep) CarModel.UpsertCarMod(_main.Settings, car.Media, CarModel.DiffAgainstStock(db, _stock, ids));
            if (!db.IsLive) _offlineModsHash = string.Join("|", _main.Settings.DbMods.Where(m => m.Enabled).Select(m => m.Sql.GetHashCode()));
            return err;
        });
        _main.SetStatus(error == null ? $"Removed {label} from {car.Media}." : "Could not remove: " + error);
        foreach (var k in _pending.Keys.Where(k => k.StartsWith($"{table}|{key}|", StringComparison.Ordinal)).ToList()) _pending.Remove(k);
        UpdateModifiedText();
        UpdateDirty();
        await LoadCarAsync(car);
    }

    private void UpdateModeBadge()
    {
        bool live = _status.DatabaseReady;
        ModeBadge.Style = (Style)FindResource(live ? "BadgeLive" : "BadgeLaunch");
        ModeTxt.Text = live ? "Live in game" : "Offline - saved for next launch";
        ModeTxt.Foreground = new SolidColorBrush(live ? Color.FromRgb(0x1E, 0x8E, 0x3E) : Color.FromRgb(0x00, 0x62, 0xCC));
        KeepCheck.Visibility = live ? Visibility.Visible : Visibility.Collapsed;
        ApplyBtn.Content = live ? "Apply" : "Save for next launch";
    }

    private void UpdateModifiedText()
    {
        bool hasMod = _car != null && _main.Settings.DbMods.Any(m => m.Name == CarModel.ModName(_car.Media) && m.Enabled);
        ModifiedTxt.Text = hasMod ? "● Modified - changes re-apply every launch" : "Stock car (no saved changes)";
    }

    // ───────────── sections ─────────────

    private void SectionList_SelectionChanged(object sender, SelectionChangedEventArgs e) => _ = LoadSectionAsync();

    private async Task LoadSectionAsync()
    {
        if (SectionList.SelectedItem is not SectionItem item || _ids == null || _db == null || _stock == null) return;
        int token = ++_loadToken;
        SectionTitle.Text = item.Def.Title;
        SectionDesc.Text = item.Def.Description;
        LoadProgress.Visibility = Visibility.Visible;
        GroupPanel.Children.Clear();
        var ids = _ids;
        var db = _db;
        var groups = await Task.Run(() => item.Def.Groups.Select(g => LoadGroup(g, ids, db)).ToList());
        if (token != _loadToken) return;
        LoadProgress.Visibility = Visibility.Collapsed;
        foreach (var gd in groups) GroupPanel.Children.Add(BuildGroupCard(gd));
        EditorScroll.ScrollToTop();
    }

    private GroupData LoadGroup(GroupDef def, CarIds ids, ICarDb db)
    {
        var gd = new GroupData { Def = def, Where = def.Where(ids), Shared = def.SharedWarning?.Invoke(ids) };
        if (gd.Where == null) return gd;
        foreach (var t in def.Tables)
        {
            if (def.Kind != GroupKind.MultiTable) { gd.Tables.Add(t); continue; }
            var n = db.Query($"SELECT COUNT(*) FROM {DbHistory.QuoteIdent(t)} WHERE {gd.Where};", out _);
            if (n is { Rows.Count: > 0 } && n.Rows[0][0] is { } c && c != "0") gd.Tables.Add(t);
        }
        foreach (var (table, column, side) in def.RowLabelRefs)
        {
            var r = db.Query($"SELECT Level, IsStock, {DbHistory.QuoteIdent(column)} FROM {DbHistory.QuoteIdent(table)} WHERE Ordinal = {ids.CarId};", out _);
            if (r == null) continue;
            foreach (var row in r.Rows)
            {
                if (row[2] == null) continue;
                var label = (row[1] == "1" ? "Stock" : $"Level {row[0]}") + " · " + side;
                gd.RefLabels[row[2]!] = gd.RefLabels.TryGetValue(row[2]!, out var prev) ? prev + ", " + label : label;
            }
        }
        if (gd.Tables.Count > 0) LoadTable(gd, gd.Tables[0], db);
        return gd;
    }

    private void LoadTable(GroupData gd, string table, ICarDb db)
    {
        gd.Table = table;
        var q = $"SELECT * FROM {DbHistory.QuoteIdent(table)} WHERE {gd.Where};";
        gd.Current = db.Query(q, out _);
        var stock = _stock!.Query(q, out _);
        gd.Stock.Clear();
        gd.Rows.Clear();
        gd.StockColumns = stock?.Columns ?? new();
        if (gd.Current == null) return;
        int key = KeyIndex(gd.Current, gd.Def.KeyColumn);
        if (stock != null && KeyIndex(stock, gd.Def.KeyColumn) is var sk and >= 0)
            foreach (var r in stock.Rows.Where(r => r[sk] != null)) gd.Stock[r[sk]!] = r;
        int lvl = gd.Current.Columns.IndexOf("Level"), isStock = gd.Current.Columns.IndexOf("IsStock");
        var rows = gd.Current.Rows.Where(r => key >= 0 && r[key] != null).ToList();
        if (lvl >= 0) rows = rows.OrderBy(r => double.TryParse(r[lvl], NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0).ToList();
        foreach (var r in rows)
        {
            var k = r[key]!;
            string label = gd.RefLabels.TryGetValue(k, out var rl) ? rl
                : lvl >= 0 && isStock >= 0 ? (r[isStock] == "1" ? $"Stock (level {r[lvl]})" : $"Upgrade level {r[lvl]}")
                : rows.Count == 1 ? "Stock" : $"Entry {k}";
            if (!gd.Stock.ContainsKey(k)) label = (lvl >= 0 ? $"Level {r[lvl]}" : label) + " · added by you";
            if (lvl >= 0 && int.TryParse(r[lvl], NumberStyles.Integer, CultureInfo.InvariantCulture, out var lv) && !Upgrades.InShop(table, lv))
                label += " · not shown in the shop (no slot for this level)";
            gd.Rows.Add((k, label));
        }
        gd.SelectedKey = isStock >= 0 ? rows.FirstOrDefault(r => r[isStock] == "1")?[key] ?? gd.Rows.FirstOrDefault().Key : gd.Rows.FirstOrDefault().Key;
    }

    private static int KeyIndex(SqlResult r, string key) => r.Columns.FindIndex(c => c.Equals(key, StringComparison.OrdinalIgnoreCase));

    // ───────────── cards & field editors ─────────────

    private Border BuildGroupCard(GroupData gd)
    {
        var card = new Border { Style = (Style)FindResource("GlassCard"), Margin = new Thickness(0, 4, 0, 8) };
        var stack = new StackPanel();
        card.Child = stack;
        var head = new Grid();
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        head.Children.Add(new TextBlock { Text = gd.Def.Title, Style = (Style)FindResource("SectionHeading") });
        if (gd.Def.AddKind is { } addKind && gd.Where != null)
        {
            var add = new Button
            {
                Content = addKind switch
                {
                    UpgradeKind.ExtraLevel => "+ Add level",
                    UpgradeKind.EngineSwap => "+ Add engine swap",
                    UpgradeKind.DrivetrainSwap => "+ Add conversion",
                    UpgradeKind.TireCompound => "+ Add compound",
                    UpgradeKind.TireWidth => "+ Add wider tyres",
                    UpgradeKind.Spacers => "+ Set spacers",
                    _ => "+ Add",
                },
                Style = (Style)FindResource("GlassBtn"), Padding = new Thickness(12, 4, 12, 4), VerticalAlignment = VerticalAlignment.Top,
            };
            add.Click += (_, _) => OpenAddDialog(addKind, addKind == UpgradeKind.ExtraLevel ? gd.Table : null);
            Grid.SetColumn(add, 1);
            head.Children.Add(add);
        }
        stack.Children.Add(head);
        if (gd.Shared != null)
            stack.Children.Add(new TextBlock { Text = "⚠ " + gd.Shared, FontSize = 12, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(Color.FromRgb(0xC9, 0x6F, 0x00)), TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 6) });
        if (gd.Def.Note != null)
            stack.Children.Add(new TextBlock { Text = gd.Def.Note, Style = (Style)FindResource("BodyTxt"), Margin = new Thickness(0, 0, 0, 8) });
        if (gd.Where == null || gd.Tables.Count == 0 || gd.Current == null || gd.Rows.Count == 0)
        {
            stack.Children.Add(new TextBlock { Text = "This car has no data here.", Style = (Style)FindResource("BodyTxt") });
            return card;
        }

        var removeBtn = new Button { Style = (Style)FindResource("GlassBtnRed"), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, 0, 8) };
        void UpdateRemove()
        {
            bool added = gd.SelectedKey != null && !gd.Stock.ContainsKey(gd.SelectedKey);
            removeBtn.Visibility = added ? Visibility.Visible : Visibility.Collapsed;
            removeBtn.Content = "Remove this upgrade you added";
        }
        removeBtn.Click += (_, _) =>
        {
            if (gd.Table != null && gd.SelectedKey != null)
                RemoveAdded(gd.Table, gd.Def.KeyColumn, gd.SelectedKey, gd.Rows.FirstOrDefault(r => r.Key == gd.SelectedKey).Label ?? gd.SelectedKey);
        };
        var fields = new WrapPanel();
        // as many columns as fit (min 260 px each), cells stretched to fill the row
        fields.SizeChanged += (_, _) => FitColumns(fields);
        fields.LayoutUpdated += (_, _) => { if (fields.Children.Count > 0 && fields.Children[0] is FrameworkElement f && double.IsNaN(f.Width)) FitColumns(fields); };
        var pickers = new Grid { Margin = new Thickness(0, 0, 0, 8) };
        pickers.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        pickers.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(12) });
        pickers.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        ComboBox? rowCombo = null;

        void FillRows()
        {
            if (rowCombo == null) return;
            rowCombo.Items.Clear();
            foreach (var (key, label) in gd.Rows) rowCombo.Items.Add(new ComboBoxItem { Content = label, Tag = key });
            rowCombo.SelectedItem = rowCombo.Items.Cast<ComboBoxItem>().FirstOrDefault(i => (string)i.Tag == gd.SelectedKey);
            rowCombo.Visibility = gd.Rows.Count > 1 ? Visibility.Visible : Visibility.Collapsed;
        }

        if (gd.Def.Kind == GroupKind.MultiTable)
        {
            var part = new ComboBox { Style = (Style)FindResource("GlassCombo") };
            foreach (var t in gd.Tables) part.Items.Add(new ComboBoxItem { Content = CarModel.TableLabel(t), Tag = t });
            part.SelectedIndex = 0;
            part.SelectionChanged += async (_, _) =>
            {
                if (part.SelectedItem is not ComboBoxItem { Tag: string t } || _db == null) return;
                var db = _db;
                await Task.Run(() => LoadTable(gd, t, db));
                FillRows();
                UpdateRemove();
                BuildFields(gd, fields);
            };
            pickers.Children.Add(Labeled("Part", part));
        }
        if (gd.Def.Kind != GroupKind.Single)
        {
            rowCombo = new ComboBox { Style = (Style)FindResource("GlassCombo") };
            rowCombo.SelectionChanged += (_, _) =>
            {
                if (rowCombo.SelectedItem is not ComboBoxItem { Tag: string key } || key == gd.SelectedKey) return;
                gd.SelectedKey = key;
                UpdateRemove();
                BuildFields(gd, fields);
            };
            var holder = Labeled(gd.Def.Kind == GroupKind.MultiTable ? "Upgrade level" : "Which one", rowCombo);
            Grid.SetColumn(holder, gd.Def.Kind == GroupKind.MultiTable ? 2 : 0);
            pickers.Children.Add(holder);
            FillRows();
        }
        if (pickers.Children.Count > 0) stack.Children.Add(pickers);
        UpdateRemove();
        stack.Children.Add(removeBtn);
        stack.Children.Add(fields);
        BuildFields(gd, fields);
        return card;
    }

    private static void FitColumns(WrapPanel panel)
    {
        double width = panel.ActualWidth;
        if (width <= 0) return;
        int columns = Math.Max(1, (int)(width / 260));
        double cell = Math.Floor(width / columns) - 12;
        foreach (FrameworkElement child in panel.Children)
            if (Math.Abs(child.Width - cell) > 0.5 || double.IsNaN(child.Width)) child.Width = cell;
    }

    private FrameworkElement Labeled(string caption, Control control)
    {
        var sp = new StackPanel();
        sp.Children.Add(new TextBlock { Text = caption, Style = (Style)FindResource("CaptionTxt") });
        sp.Children.Add(control);
        return sp;
    }

    private void BuildFields(GroupData gd, WrapPanel panel)
    {
        panel.Children.Clear();
        if (gd.Current == null || gd.SelectedKey == null || gd.Table == null) return;
        int key = KeyIndex(gd.Current, gd.Def.KeyColumn);
        var row = gd.Current.Rows.FirstOrDefault(r => r[key] == gd.SelectedKey);
        if (row == null) return;
        gd.Stock.TryGetValue(gd.SelectedKey, out var stockRow);
        IEnumerable<string> columns = gd.Def.Fields ?? gd.Current.Columns.Where(c => !CarModel.HiddenColumns.Contains(c));
        foreach (var col in columns)
        {
            int i = gd.Current.Columns.IndexOf(col);
            if (i < 0) continue;
            int si = gd.StockColumns.IndexOf(col);
            string? current = row[i];
            string? stock = stockRow != null && si >= 0 ? stockRow[si] : null;
            bool numeric = double.TryParse(current ?? stock, NumberStyles.Float, CultureInfo.InvariantCulture, out _);
            if (gd.Def.Fields == null && !numeric) continue;   // text/blob columns are not editable here
            panel.Children.Add(BuildField(gd.Table, gd.Def.KeyColumn, gd.SelectedKey, col, current, stock));
        }
    }

    private FrameworkElement BuildField(string table, string keyColumn, string key, string column, string? current, string? stock)
    {
        var meta = CarModel.MetaFor(column);
        var id = $"{table}|{key}|{column}";
        _pending.TryGetValue(id, out var pend);
        string? shown = pend?.Value ?? current;

        var cell = new Grid { Margin = new Thickness(0, 0, 12, 8) };
        cell.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(4) });
        cell.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var marker = new Border { CornerRadius = new CornerRadius(2), Margin = new Thickness(0, 2, 0, 2) };
        cell.Children.Add(marker);

        var body = new StackPanel { Margin = new Thickness(8, 0, 0, 0) };
        Grid.SetColumn(body, 1);
        cell.Children.Add(body);
        var label = new TextBlock
        {
            Text = meta.Label + (meta.Unit != null ? $"  ({meta.Unit})" : ""), FontSize = 11, FontWeight = FontWeights.SemiBold,
            Foreground = new SolidColorBrush(Color.FromRgb(0x48, 0x48, 0x4A)), TextTrimming = TextTrimming.CharacterEllipsis, Margin = new Thickness(0, 0, 0, 3),
            ToolTip = (meta.Help != null ? meta.Help + "\n\n" : "") + $"{table}.{column}",
        };
        body.Children.Add(label);

        var line = new Grid();
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(130) });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        body.Children.Add(line);

        var stockTxt = new TextBlock { FontSize = 11, Foreground = new SolidColorBrush(Color.FromRgb(0x8E, 0x8E, 0x93)), VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(8, 0, 4, 0), TextTrimming = TextTrimming.CharacterEllipsis };
        var reset = new Button { Content = "↺", Style = (Style)FindResource("GlassBtn"), Padding = new Thickness(8, 2, 8, 2), Margin = new Thickness(0), ToolTip = "Back to the stock value" };
        Grid.SetColumn(stockTxt, 1);
        Grid.SetColumn(reset, 2);
        line.Children.Add(stockTxt);
        line.Children.Add(reset);

        Func<string?> read;
        Action<string?> write;
        Control editor;
        Func<string?, string> pretty = v => v ?? "NULL";

        if (_options.TryGetValue(column, out var opts))
        {
            var combo = new ComboBox { Style = (Style)FindResource("GlassCombo"), Margin = new Thickness(0) };
            foreach (var (v, l) in opts) combo.Items.Add(new ComboBoxItem { Content = l, Tag = v });
            if (shown != null && opts.All(o => !CarModel.SameValue(o.Value, shown))) combo.Items.Add(new ComboBoxItem { Content = shown, Tag = shown });
            read = () => (combo.SelectedItem as ComboBoxItem)?.Tag as string;
            write = v => combo.SelectedItem = combo.Items.Cast<ComboBoxItem>().FirstOrDefault(x => CarModel.SameValue((string)x.Tag, v));
            pretty = v => opts.FirstOrDefault(o => CarModel.SameValue(o.Value, v)).Label ?? v ?? "NULL";
            editor = combo;
            write(shown);
            combo.SelectionChanged += (_, _) => Changed();
        }
        else if (CarModel.IsFlag(column, stock ?? current))
        {
            var check = new CheckBox { Content = "On", Margin = new Thickness(0, 4, 0, 4) };
            read = () => check.IsChecked == true ? "1" : "0";
            write = v => check.IsChecked = v == "1";
            pretty = v => v == "1" ? "on" : "off";
            editor = check;
            write(shown);
            check.Click += (_, _) => Changed();
        }
        else
        {
            var box = new TextBox { Style = (Style)FindResource("GlassTextBox"), FontSize = 12, Padding = new Thickness(8, 4, 8, 4) };
            read = () => box.Text.Trim().Replace(',', '.');
            write = v => box.Text = v ?? "";
            editor = box;
            write(shown);
            box.TextChanged += (_, _) => Changed();
        }
        line.Children.Add(editor);
        Refresh();
        reset.Click += (_, _) => { write(stock); Changed(); };
        return cell;

        void Changed()
        {
            var v = read();
            bool valid = v == null || v.Length > 0 && (!double.TryParse(current ?? stock, NumberStyles.Float, CultureInfo.InvariantCulture, out _) ||
                                                       double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out _));
            if (valid && CarModel.SameValue(v, current)) _pending.Remove(id);
            else _pending[id] = new PendingEdit { Table = table, KeyColumn = keyColumn, Key = key, Column = column, Current = current, Stock = stock, Value = v, Valid = valid };
            Refresh();
            UpdateDirty();
        }

        void Refresh()
        {
            _pending.TryGetValue(id, out var p);
            var effective = p?.Value ?? current;
            bool differsFromStock = stock != null && !CarModel.SameValue(effective, stock);
            marker.Background = p == null ? (differsFromStock ? ModdedBrush : Brushes.Transparent) : p.Valid ? PendingBrush : ErrorBrush;
            marker.ToolTip = p == null ? (differsFromStock ? "Changed from stock (applied)" : null) : p.Valid ? "Not applied yet" : "Not a valid number";
            if (editor is TextBox tb) tb.BorderBrush = p is { Valid: false } ? ErrorBrush : p != null ? PendingBrush : NormalBorder;
            stockTxt.Text = stock == null ? "" : differsFromStock ? $"stock {pretty(stock)}" : "stock";
            reset.Visibility = differsFromStock ? Visibility.Visible : Visibility.Hidden;
        }
    }

    // ───────────── apply / discard / reset ─────────────

    private void UpdateDirty()
    {
        int n = _pending.Count;
        bool invalid = _pending.Values.Any(p => !p.Valid);
        var c = invalid ? Color.FromRgb(0xFF, 0x3B, 0x30) : n > 0 ? Color.FromRgb(0xFF, 0x95, 0x00) : Color.FromRgb(0x34, 0xC7, 0x59);
        DirtyDot.Fill = new SolidColorBrush(c);
        DirtyTxt.Foreground = new SolidColorBrush(invalid ? Color.FromRgb(0xFF, 0x3B, 0x30) : n > 0 ? Color.FromRgb(0xC9, 0x6F, 0x00) : Color.FromRgb(0x1E, 0x8E, 0x3E));
        DirtyTxt.Text = invalid ? "Fix the values marked red before applying"
            : n > 0 ? $"{n} change(s) not applied yet" : "No unapplied changes";
        ApplyBtn.IsEnabled = n > 0 && !invalid;
        DiscardBtn.IsEnabled = n > 0;
        foreach (var s in _sections)
        {
            int count = _pending.Values.Count(p => s.Def.Groups.Any(g =>
                g.Tables.Contains(p.Table) && (g.Fields == null || g.Fields.Contains(p.Column, StringComparer.OrdinalIgnoreCase))));
            s.Badge = count > 0 ? $"{count} not applied" : "";
        }
        SectionList.Items.Refresh();
    }

    private async void Apply_Click(object sender, RoutedEventArgs e)
    {
        if (_car == null || _ids == null || _stock == null || _pending.Count == 0) return;
        var car = _car;
        var ids = _ids;
        bool keep = !_status.DatabaseReady || KeepCheck.IsChecked == true;
        var statements = _pending.Values.GroupBy(p => (p.Table, p.KeyColumn, p.Key))
            .Select(g => CarModel.UpdateSql(g.Key.Table, g.Key.KeyColumn, g.Key.Key, g.Select(p => (p.Column, p.Value)))).ToList();
        if (_pending.Values.FirstOrDefault(p => p.Table == "Data_Drivetrain" && p.Column.Equals("DrivetypeID", StringComparison.OrdinalIgnoreCase)) is { } drive)
            statements.Add(CarModel.UpdateSql("Data_Car", "Id", car.Id.ToString(CultureInfo.InvariantCulture), new[] { ("DriveTypeID", drive.Value) }));
        int n = _pending.Count;
        ApplyBtn.IsEnabled = false;
        var (error, live) = await Task.Run(() =>
        {
            var db = CurrentDb();
            var err = db.Execute(string.Join("\n", statements), $"{car.Media}: {n} change(s)");
            if (err == null && keep) CarModel.UpsertCarMod(_main.Settings, car.Media, CarModel.DiffAgainstStock(db, _stock, ids));
            if (!db.IsLive) _offlineModsHash = string.Join("|", _main.Settings.DbMods.Where(m => m.Enabled).Select(m => m.Sql.GetHashCode()));
            return (err, db.IsLive);
        });
        if (error != null)
        {
            _main.SetStatus("The game rejected the change: " + error);
            UpdateDirty();
            return;
        }
        _pending.Clear();
        _main.SetStatus(live
            ? $"Applied {n} change(s) to {car.Media}.{(keep ? " Kept for future launches." : "")} Re-select the car to feel it. Undo under Database ▸ History."
            : $"Saved {n} change(s) to {car.Media}. They apply automatically when you start the game.");
        _main.HomePage.RefreshSummary();
        UpdateModifiedText();
        UpdateDirty();
        await LoadCarAsync(car);
    }

    private void Discard_Click(object sender, RoutedEventArgs e)
    {
        _pending.Clear();
        UpdateDirty();
        _ = LoadSectionAsync();
    }

    private async void ResetCar_Click(object sender, RoutedEventArgs e)
    {
        if (_car == null || _ids == null || _stock == null) return;
        var car = _car;
        var ids = _ids;
        if (MessageBox.Show($"Put every value of {car.Media} back to stock?\n\nThis also removes its saved mod, so it stays stock after restarts.",
                "Reset car to stock", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        _pending.Clear();
        var error = await Task.Run(() =>
        {
            var db = CurrentDb();
            var toStock = CarModel.DiffAgainstStock(db, _stock, ids, towardsStock: true);
            var err = toStock.Length > 0 ? db.Execute(toStock, $"{car.Media}: reset to stock") : null;
            CarModel.UpsertCarMod(_main.Settings, car.Media, "");
            return err;
        });
        _main.SetStatus(error == null ? $"{car.Media} is back to stock." : "Reset failed: " + error);
        _main.HomePage.RefreshSummary();
        UpdateModifiedText();
        UpdateDirty();
        await LoadCarAsync(car);
    }
}
