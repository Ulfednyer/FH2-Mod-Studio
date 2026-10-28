using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using FH2ModStudio.Core;

namespace FH2ModStudio.Views;

public sealed record KindItem(UpgradeKind Kind, string Title, string Hint);

/// <summary>One dialog for every way of adding an upgrade; opened preselected from wherever the user started.</summary>
public partial class AddUpgradeWindow : Window
{
    public static readonly KindItem[] Kinds =
    {
        new(UpgradeKind.Aspiration, "Turbo or supercharger", "Add a single / twin / quad turbo or a supercharger option"),
        new(UpgradeKind.EngineSwap, "Engine swap", "Offer another car's engine in the upgrade shop"),
        new(UpgradeKind.DrivetrainSwap, "Drivetrain conversion", "Add an FWD / RWD / AWD conversion"),
        new(UpgradeKind.TireCompound, "Tyre compound", "Fill an empty tyre slot: street, sport, race, slick or rally"),
        new(UpgradeKind.TireWidth, "Wider tyres", "Add a wider front and/or rear tyre option"),
        new(UpgradeKind.Spacers, "Wheel spacers", "Wider track: always fitted, or sold in the shop"),
        new(UpgradeKind.BodyPart, "Body & aero parts / removal", "Remove hood, front/rear bumper, rear wing, side skirts, or unlock aero tuning"),
        new(UpgradeKind.ExtraLevel, "Missing level of a part", "Fill an empty shop slot, e.g. street springs or a sport anti-roll bar"),
    };

    private readonly ICarDb _db, _stock;
    private readonly CarIds _ids;
    private RadioButton? _modeFixed, _modeShop;
    private StackPanel? _priceRow;
    private TextBlock? _modeNote;
    private readonly string? _initialTable;
    private UpgradeKind _kind;
    private int _token;

    private ComboBox? _partCombo, _driveCombo;
    private ListBox? _donorList;
    private TextBox? _search, _price, _mass, _front, _rear;
    private CheckBox? _frontCheck, _rearCheck;
    private List<Donor> _donors = new();
    private (double F, double R) _stockWidths;

    public string? ResultSql { get; private set; }
    public string ResultDescription { get; private set; } = "";
    public string ResultWhere { get; private set; } = "";

    public AddUpgradeWindow(ICarDb db, ICarDb stock, CarIds ids, UpgradeKind kind, string? table = null)
    {
        InitializeComponent();
        _db = db;
        _stock = stock;
        _ids = ids;
        _initialTable = table;
        TitleTxt.Text = $"Add upgrade - {ids.Media}";
        KindList.ItemsSource = Kinds;
        SourceInitialized += (_, _) => GlassHelper.EnableAcrylic(this);
        KeyDown += (_, e) => { if (e.Key == Key.Escape) Close(); };
        KindList.SelectedItem = Kinds.First(k => k.Kind == kind);
    }

    private void TitleBar_MouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton == MouseButton.Left) DragMove();
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) => Close();

    private async void KindList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (KindList.SelectedItem is not KindItem k) return;
        try
        {
            await BuildOptionsAsync(k.Kind);
        }
        catch (Exception ex)
        {
            PreviewTxt.Text = "Could not load the options: " + ex.Message;
            PreviewTxt.Foreground = new SolidColorBrush(Color.FromRgb(0xFF, 0x3B, 0x30));
            AddBtn.IsEnabled = false;
        }
    }

    // ───────────── building the options for a kind ─────────────

    private TextBlock Heading(string text) => new() { Text = text, Style = (Style)FindResource("SectionHeading") };
    private TextBlock Body(string text) => new() { Text = text, Style = (Style)FindResource("BodyTxt"), Margin = new Thickness(0, 0, 0, 10) };

    private TextBox Field(string caption, string value, string? unit = null)
    {
        var box = new TextBox { Style = (Style)FindResource("GlassTextBox"), FontSize = 12, Padding = new Thickness(8, 5, 8, 5), Width = 160, Text = value, HorizontalAlignment = HorizontalAlignment.Left };
        box.TextChanged += (_, _) => UpdatePreview();
        var row = new StackPanel { Margin = new Thickness(0, 0, 0, 8) };
        row.Children.Add(new TextBlock { Text = caption + (unit != null ? $"  ({unit})" : ""), Style = (Style)FindResource("CaptionTxt") });
        row.Children.Add(box);
        OptionsPanel.Children.Add(row);
        return box;
    }

    private ComboBox Combo(string caption, IEnumerable<(string Value, string Label)> items)
    {
        var combo = new ComboBox { Style = (Style)FindResource("GlassCombo"), Width = 340, HorizontalAlignment = HorizontalAlignment.Left };
        foreach (var (v, l) in items) combo.Items.Add(new ComboBoxItem { Content = l, Tag = v });
        combo.SelectedIndex = 0;
        var row = new StackPanel { Margin = new Thickness(0, 0, 0, 8) };
        row.Children.Add(new TextBlock { Text = caption, Style = (Style)FindResource("CaptionTxt") });
        row.Children.Add(combo);
        OptionsPanel.Children.Add(row);
        return combo;
    }

    private void DonorList(string caption)
    {
        OptionsPanel.Children.Add(new TextBlock { Text = caption, Style = (Style)FindResource("CaptionTxt") });
        var grid = new Grid { Margin = new Thickness(0, 0, 0, 6) };
        _search = new TextBox { Style = (Style)FindResource("GlassTextBox"), FontSize = 12, Padding = new Thickness(8, 5, 8, 5) };
        var hint = new TextBlock { Text = "Search…", FontSize = 12, Foreground = new SolidColorBrush(Color.FromRgb(0x8E, 0x8E, 0x93)), Margin = new Thickness(10, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false };
        _search.TextChanged += (_, _) => { hint.Visibility = _search.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed; FilterDonors(); };
        grid.Children.Add(_search);
        grid.Children.Add(hint);
        OptionsPanel.Children.Add(grid);
        _donorList = new ListBox
        {
            Height = 230, Background = Brushes.Transparent, BorderThickness = new Thickness(0),
            ItemContainerStyle = (Style)FindResource("MacroListItem"), ItemTemplate = (DataTemplate)FindResource("DonorTemplate"),
        };
        ScrollViewer.SetHorizontalScrollBarVisibility(_donorList, ScrollBarVisibility.Disabled);
        _donorList.SelectionChanged += (_, _) => DonorChanged();
        OptionsPanel.Children.Add(_donorList);
    }

    private void FilterDonors()
    {
        if (_donorList == null) return;
        var terms = (_search?.Text ?? "").Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var list = _donors.Where(d => terms.All(t => d.Title.Contains(t, StringComparison.OrdinalIgnoreCase) || d.Detail.Contains(t, StringComparison.OrdinalIgnoreCase))).ToList();
        var selected = _donorList.SelectedItem;
        _donorList.ItemsSource = list;
        _donorList.SelectedItem = selected != null && list.Contains(selected) ? selected : list.FirstOrDefault();
    }

    private async Task SafeLoad(Func<List<Donor>> load)
    {
        try
        {
            await LoadDonorsAsync(load);
        }
        catch (Exception ex)
        {
            PreviewTxt.Text = "Could not load the options: " + ex.Message;
            PreviewTxt.Foreground = new SolidColorBrush(Color.FromRgb(0xFF, 0x3B, 0x30));
        }
    }

    private async Task LoadDonorsAsync(Func<List<Donor>> load)
    {
        int token = ++_token;
        PreviewTxt.Text = "Loading…";
        var donors = await Task.Run(load);
        if (token != _token) return;
        _donors = donors;
        PreviewTxt.Text = "";
        FilterDonors();
        UpdatePreview();
    }

    private async Task BuildOptionsAsync(UpgradeKind kind)
    {
        _kind = kind;
        _token++;
        OptionsPanel.Children.Clear();
        _partCombo = _driveCombo = null;
        _donorList = null;
        _search = _price = _mass = _front = _rear = null;
        _frontCheck = _rearCheck = null;
        _modeFixed = _modeShop = null;
        _priceRow = null;
        _modeNote = null;
        _donors = new();

        switch (kind)
        {
            case UpgradeKind.Aspiration:
                OptionsPanel.Children.Add(Heading("Turbo or supercharger"));
                OptionsPanel.Children.Add(Body("The values (boost, levels, prices) are copied from another engine that has this part. The closest engine is picked for you; you can fine-tune everything afterwards."));
                var have = await Task.Run(() => Upgrades.AspirationParts.Where(p => _db.Query($"SELECT COUNT(*) FROM {DbHistory.QuoteIdent(p.Table)} WHERE EngineID = {_ids.EngineId};", out _)?.Rows[0][0] is { } c && c != "0").Select(p => p.Table).ToHashSet());
                _partCombo = Combo("Type", Upgrades.AspirationParts.Select(p => (p.Table, have.Contains(p.Table) ? p.Label + "  (already has it - only fills missing levels)" : p.Label)));
                var first = Upgrades.AspirationParts.FirstOrDefault(p => !have.Contains(p.Table) && p.Table.Contains("TurboTwin")).Table
                            ?? Upgrades.AspirationParts.FirstOrDefault(p => !have.Contains(p.Table)).Table
                            ?? Upgrades.AspirationParts[0].Table;
                _partCombo.SelectedItem = _partCombo.Items.Cast<ComboBoxItem>().First(i => (string)i.Tag == first);

                var aspModes = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 6) };
                _modeFixed = new RadioButton { Content = "Direct upgrade", Style = (Style)FindResource("SegmentBtn"), GroupName = "aspMode" };
                _modeShop = new RadioButton { Content = "Shop conversion", Style = (Style)FindResource("SegmentBtn"), GroupName = "aspMode" };
                var modeBoth = new RadioButton { Content = "Both", Style = (Style)FindResource("SegmentBtn"), GroupName = "aspMode", IsChecked = true };
                aspModes.Children.Add(_modeFixed);
                aspModes.Children.Add(_modeShop);
                aspModes.Children.Add(modeBoth);
                OptionsPanel.Children.Add(new TextBlock { Text = "Aspiration installation mode", Style = (Style)FindResource("CaptionTxt") });
                OptionsPanel.Children.Add(new Border { Background = new SolidColorBrush(Color.FromArgb(0x14, 0, 0, 0)), CornerRadius = new CornerRadius(10), Padding = new Thickness(2), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, 0, 8), Child = aspModes });

                DonorList("Copy the values from");
                _partCombo.SelectionChanged += async (_, _) => { var p = SelectedPart()!; await SafeLoad(() => Upgrades.AspirationDonors(_db, _ids, p)); };
                var part = SelectedPart()!;
                await LoadDonorsAsync(() => Upgrades.AspirationDonors(_db, _ids, part));
                break;

            case UpgradeKind.EngineSwap:
                OptionsPanel.Children.Add(Heading("Engine swap"));
                OptionsPanel.Children.Add(Body("Adds another car's engine as a conversion in the upgrade shop. Engines the game itself already uses as swaps are listed first."));
                DonorList("Engine");
                _price = Field("Price", "25000", "CR");
                _mass = Field("Weight change", "0", "kg");
                await LoadDonorsAsync(() => Upgrades.EngineDonors(_db, _ids));
                break;

            case UpgradeKind.DrivetrainSwap:
                OptionsPanel.Children.Add(Heading("Drivetrain conversion"));
                OptionsPanel.Children.Add(Body("Adds a drive-type conversion using another car's drivetrain (its gearbox, differential and clutch)."));
                _driveCombo = Combo("Convert to", new[] { ("3", "AWD"), ("2", "RWD"), ("1", "FWD") });
                DonorList("Use the drivetrain of");
                _price = Field("Price", "5000", "CR");
                _mass = Field("Weight change", "60", "kg");
                _driveCombo.SelectionChanged += async (_, _) => { var dt = SelectedDrive(); await SafeLoad(() => Upgrades.DrivetrainDonors(_db, _ids, dt)); };
                var drive = SelectedDrive();
                await LoadDonorsAsync(() => Upgrades.DrivetrainDonors(_db, _ids, drive));
                break;

            case UpgradeKind.TireCompound:
                OptionsPanel.Children.Add(Heading("Tyre compound"));
                OptionsPanel.Children.Add(Body("The tyre shop has fixed slots (street, sport, race, rally) and shows one tyre per slot, so only the slots this car doesn't fill yet are listed. To use a different compound in a slot it already has, change it under Tyres & grip."));
                DonorList("Slot");
                _price = Field("Price", "6000", "CR");
                await LoadDonorsAsync(() => Upgrades.TireCompounds(_db, _ids));
                break;

            case UpgradeKind.TireWidth:
                OptionsPanel.Children.Add(Heading("Wider tyres"));
                _stockWidths = await Task.Run(() => Upgrades.StockTireWidths(_db, _ids));
                OptionsPanel.Children.Add(Body($"Stock widths: front {_stockWidths.F} mm, rear {_stockWidths.R} mm. Wider tyres give more grip. Adds a new tyre-width level."));
                _frontCheck = new CheckBox { Content = "Front", IsChecked = true };
                _frontCheck.Click += (_, _) => UpdatePreview();
                OptionsPanel.Children.Add(_frontCheck);
                _front = Field("New front width", (_stockWidths.F + 40).ToString(CultureInfo.InvariantCulture), "mm");
                _rearCheck = new CheckBox { Content = "Rear", IsChecked = true };
                _rearCheck.Click += (_, _) => UpdatePreview();
                OptionsPanel.Children.Add(_rearCheck);
                _rear = Field("New rear width", (_stockWidths.R + 40).ToString(CultureInfo.InvariantCulture), "mm");
                _price = Field("Price", "3000", "CR");
                break;

            case UpgradeKind.Spacers:
                OptionsPanel.Children.Add(Heading("Wheel spacers"));
                OptionsPanel.Children.Add(Body("Pushes the wheels outward by widening the car's track. Mainly visual fitment - the effect on handling is small. Re-select the car in your garage to see it."));
                var (fixedMm, shop) = await Task.Run(() => (Upgrades.SpacerMm(_db, _stock, _ids, _ids.BodyId ?? 0), Upgrades.ShopSpacer(_db, _ids)));
                var shopMm = shop is { } sp ? await Task.Run(() => Upgrades.SpacerMm(_db, _stock, _ids, sp.BodyId)) : (Front: 15.0, Rear: 15.0);
                string Txt(double v) => v.ToString(CultureInfo.InvariantCulture);

                var modes = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 6) };
                _modeFixed = new RadioButton { Content = "Always fitted", Style = (Style)FindResource("SegmentBtn"), GroupName = "spacerMode", IsChecked = true };
                _modeShop = new RadioButton { Content = "Buy in the shop", Style = (Style)FindResource("SegmentBtn"), GroupName = "spacerMode" };
                modes.Children.Add(_modeFixed);
                modes.Children.Add(_modeShop);
                OptionsPanel.Children.Add(new TextBlock { Text = "How the car gets them", Style = (Style)FindResource("CaptionTxt") });
                OptionsPanel.Children.Add(new Border { Background = new SolidColorBrush(Color.FromArgb(0x14, 0, 0, 0)), CornerRadius = new CornerRadius(10), Padding = new Thickness(2), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, 0, 6), Child = modes });
                _modeNote = Body("");
                OptionsPanel.Children.Add(_modeNote);

                var presets = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 8) };
                foreach (var mm in new[] { 0, 10, 15, 20, 30 })
                {
                    var b = new Button { Content = mm == 0 ? "None" : $"+{mm} mm", Style = (Style)FindResource("GlassBtn") };
                    b.Click += (_, _) => { foreach (var box in new[] { _front, _rear }) if (box != null) box.Text = mm.ToString(CultureInfo.InvariantCulture); };
                    presets.Children.Add(b);
                }
                OptionsPanel.Children.Add(new TextBlock { Text = "Quick presets (front and rear)", Style = (Style)FindResource("CaptionTxt") });
                OptionsPanel.Children.Add(presets);
                _front = Field("Front spacer per side", Txt(fixedMm.Front), "mm");
                _rear = Field("Rear spacer per side", Txt(fixedMm.Rear), "mm");
                _price = Field("Price in the shop", Txt(shop?.Price ?? 800), "CR");
                _priceRow = _price.Parent as StackPanel;
                var (shopBtn, frontBox, rearBox, note) = (_modeShop, _front, _rear, _modeNote);

                void ModeChanged()
                {
                    bool shopMode = shopBtn.IsChecked == true;
                    var mm = shopMode ? shopMm : fixedMm;
                    frontBox.Text = Txt(mm.Front);
                    rearBox.Text = Txt(mm.Rear);
                    if (_priceRow != null) _priceRow.Visibility = shopMode ? Visibility.Visible : Visibility.Collapsed;
                    note.Text = shopMode
                        ? (shop != null ? "This car already has a shop spacer upgrade - this changes its size and price. " : "Adds a body upgrade to the shop that fits the spacers when bought. ") +
                          "While it's fitted, the front bumper is not drawn, and tyre-width, weight, chassis and bumper upgrades you had must be picked again in the shop. " +
                          "Before removing it here, switch back to the stock body in the shop. Keep 'Keep after game restart' ticked so your garage never points at a missing part."
                        : "Fitted to every copy of this car, keeps every body part. It isn't a shop item - set 0 mm here to take the spacers off.";
                    UpdatePreview();
                }
                _modeFixed.Checked += (_, _) => ModeChanged();
                _modeShop.Checked += (_, _) => ModeChanged();
                ModeChanged();
                break;

            case UpgradeKind.BodyPart:
                OptionsPanel.Children.Add(Heading("Body & aero parts / removal"));
                OptionsPanel.Children.Add(Body("Adds a body part removal upgrade (Level 4, RequiresGraphics = 0) to hide that 3D part mesh in game, or unlocks aero downforce tuning on stock/locked parts."));
                _driveCombo = Combo("Upgrade option", new[]
                {
                    ("hood", "Remove Hood (Level 4 - exposed engine bay)"),
                    ("front_bumper", "Remove Front Bumper (Level 4)"),
                    ("rear_bumper", "Remove Rear Bumper (Level 4)"),
                    ("rear_wing", "Remove Rear Wing (Level 4)"),
                    ("side_skirts", "Remove Side Skirts (Level 4)"),
                    ("unlock_aero", "Unlock Aero Downforce Tuning (all wing & bumper levels)"),
                });
                _price = Field("Price in shop", "100", "CR");
                _mass = Field("Weight change", "-2", "kg");
                _driveCombo.SelectionChanged += (_, _) =>
                {
                    var opt = SelectedDrive();
                    if (_price != null) _price.Text = opt == "unlock_aero" ? "0" : "100";
                    if (_mass != null) _mass.Text = opt == "hood" ? "-3" : opt == "unlock_aero" ? "0" : "-2";
                    UpdatePreview();
                };
                break;

            case UpgradeKind.ExtraLevel:
                OptionsPanel.Children.Add(Heading("Missing level of a part"));
                OptionsPanel.Children.Add(Body("The upgrade shop has a fixed number of levels per part (for springs: stock, street, sport, race, rally) and only shows those. " +
                                               "So a part can only gain a level the car doesn't have yet. The new level starts as a copy of the nearest one - change its values afterwards in the car's sections."));
                var tables = CarModel.Sections.SelectMany(s => s.Groups).Where(g => g.AddKind == UpgradeKind.ExtraLevel).SelectMany(g => g.Tables).Distinct().ToList();
                var slots = await Task.Run(() => Upgrades.LevelSlots(_db, _ids, tables));
                var open = slots.Where(s => s.Level >= 0).ToList();
                var full = slots.Where(s => s.Level < 0).Select(s => CarModel.TableLabel(s.Table)).ToList();
                if (open.Count > 0)
                {
                    _partCombo = Combo("Part and level", open.Select(s => ($"{s.Table}|{s.Level}",
                        $"{CarModel.TableLabel(s.Table)} - level {s.Level}{(s.StockLevel is { } st && s.Level < st ? $" (below stock level {st})" : "")}   · has {string.Join(", ", s.Used)}")));
                    var pick = open.FirstOrDefault(s => s.Table == _initialTable && s.Level > (s.StockLevel ?? -1)) ?? open.FirstOrDefault(s => s.Table == _initialTable)
                               ?? open.FirstOrDefault(s => s.Level > (s.StockLevel ?? -1)) ?? open[0];
                    _partCombo.SelectedItem = _partCombo.Items.Cast<ComboBoxItem>().First(i => (string)i.Tag == $"{pick.Table}|{pick.Level}");
                    _partCombo.SelectionChanged += (_, _) => UpdatePreview();
                }
                if (full.Count > 0)
                    OptionsPanel.Children.Add(Body("No stronger level fits for: " + string.Join(", ", full) + " - every shop level above stock is taken. " +
                                                   "To go further, make the top level stronger in the car's sections (e.g. stiffer race springs)."));
                break;
        }
        UpdatePreview();
    }

    private string? SelectedPart() => (_partCombo?.SelectedItem as ComboBoxItem)?.Tag as string;
    private string SelectedDrive() => (_driveCombo?.SelectedItem as ComboBoxItem)?.Tag as string ?? "3";
    private Donor? SelectedDonor() => _donorList?.SelectedItem as Donor;

    private void DonorChanged()
    {
        if (_kind == UpgradeKind.EngineSwap && SelectedDonor() is { } d && _mass != null && _ids.EngineId is { } mine)
        {
            var donor = d.Key;
            _ = Task.Run(() => Upgrades.EngineMass(_db, donor) - Upgrades.EngineMass(_db, mine.ToString(CultureInfo.InvariantCulture)))
                .ContinueWith(t => Dispatcher.Invoke(() => _mass.Text = Math.Round(t.Result, 1).ToString(CultureInfo.InvariantCulture)));
        }
        if (_kind == UpgradeKind.TireCompound && SelectedDonor() is { } slot && _price != null)
            _price.Text = Upgrades.CompoundSlotPrice(slot.Key).ToString(CultureInfo.InvariantCulture);
        UpdatePreview();
    }

    private static bool Num(TextBox? box, out double v) =>
        double.TryParse((box?.Text ?? "").Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out v);

    // ───────────── preview & validation ─────────────

    private string? Validate()
    {
        switch (_kind)
        {
            case UpgradeKind.TireCompound when _donorList != null && _donors.Count == 0 && PreviewTxt.Text != "Loading…":
                return "This car already fills every tyre slot of the shop. Change a compound under Tyres & grip instead.";
            case UpgradeKind.Aspiration:
            case UpgradeKind.TireCompound:
                return SelectedDonor() == null ? "Pick an option from the list." : _price != null && !Num(_price, out _) ? "Enter a price." : null;
            case UpgradeKind.EngineSwap:
            case UpgradeKind.DrivetrainSwap:
                if (SelectedDonor() == null) return "Pick an option from the list.";
                return !Num(_price, out _) || !Num(_mass, out _) ? "Price and weight change must be numbers." : null;
            case UpgradeKind.TireWidth:
                if (_frontCheck?.IsChecked != true && _rearCheck?.IsChecked != true) return "Choose front, rear or both.";
                if (_frontCheck?.IsChecked == true && (!Num(_front, out var f) || f < 100 || f > 500)) return "Front width must be between 100 and 500 mm.";
                if (_rearCheck?.IsChecked == true && (!Num(_rear, out var r) || r < 100 || r > 500)) return "Rear width must be between 100 and 500 mm.";
                return Num(_price, out _) ? null : "Enter a price.";
            case UpgradeKind.Spacers:
                foreach (var b in new[] { _front, _rear })
                    if (!Num(b, out var mm) || mm < -30 || mm > 80) return "Spacers must be between -30 and 80 mm per side.";
                if (_modeShop?.IsChecked == true && !Num(_price, out _)) return "Enter a price.";
                return null;
            case UpgradeKind.BodyPart:
                return !Num(_price, out _) || !Num(_mass, out _) ? "Price and weight change must be numbers." : null;
            case UpgradeKind.ExtraLevel:
                return SelectedPart() == null ? "Every part of this car already uses all of its shop levels - there is no free level to add." : null;
        }
        return null;
    }

    private void UpdatePreview()
    {
        var error = Validate();
        AddBtn.IsEnabled = error == null;
        if (error != null) { PreviewTxt.Text = error; PreviewTxt.Foreground = new SolidColorBrush(Color.FromRgb(0xC9, 0x6F, 0x00)); return; }
        PreviewTxt.Foreground = new SolidColorBrush(Color.FromRgb(0x48, 0x48, 0x4A));
        var d = SelectedDonor();
        PreviewTxt.Text = _kind switch
        {
            UpgradeKind.Aspiration => $"Adds {((ComboBoxItem)_partCombo!.SelectedItem).Content.ToString()!.Split("  (")[0].ToLowerInvariant()} levels to this car's engine, copied from {d!.Title}.",
            UpgradeKind.EngineSwap => $"Adds the {d!.Title} as an engine swap for {_price!.Text} CR.",
            UpgradeKind.DrivetrainSwap => $"Adds a {((ComboBoxItem)_driveCombo!.SelectedItem).Content} conversion ({d!.Title}) for {_price!.Text} CR.",
            UpgradeKind.TireCompound => $"Puts {d!.Title.ToLowerInvariant()} into tyre shop slot {d.Key} for {_price!.Text} CR.",
            UpgradeKind.TireWidth => $"Adds a tyre-width level: {(_frontCheck!.IsChecked == true ? $"front {_front!.Text} mm " : "")}{(_rearCheck!.IsChecked == true ? $"rear {_rear!.Text} mm" : "")}.",
            UpgradeKind.Spacers => _modeShop?.IsChecked == true
                ? $"Sells front {_front!.Text} mm / rear {_rear!.Text} mm spacers in the shop for {_price!.Text} CR. Front bumper is hidden while fitted."
                : $"Always fits front {_front!.Text} mm / rear {_rear!.Text} mm spacers per side from the next car load.",
            UpgradeKind.BodyPart => SelectedDrive() == "unlock_aero"
                ? "Unlocks aero downforce tuning on this car's wings and bumpers, making front and rear downforce fully adjustable in the tuning menu."
                : $"Adds {((ComboBoxItem)_driveCombo!.SelectedItem).Content.ToString()!.Split(" (")[0]} for {_price!.Text} CR ({_mass!.Text} kg weight change).",
            UpgradeKind.ExtraLevel => $"Adds {((ComboBoxItem)_partCombo!.SelectedItem).Content!.ToString()!.Split("   ·")[0]} to the upgrade shop, starting as a copy of the nearest level.",
            _ => "",
        };
    }

    private async void Add_Click(object sender, RoutedEventArgs e)
    {
        if (Validate() != null) return;
        AddBtn.IsEnabled = false;
        var d = SelectedDonor();
        string part = SelectedPart() ?? "", drive = SelectedDrive();
        Num(_price, out var price);
        Num(_mass, out var mass);
        Num(_front, out var front);
        Num(_rear, out var rear);
        bool shopMode = _modeShop?.IsChecked == true;
        bool useFront = _frontCheck?.IsChecked == true, useRear = _rearCheck?.IsChecked == true;
        string partLabel = (_partCombo?.SelectedItem as ComboBoxItem)?.Content?.ToString()?.Split("  (")[0].Split("   ·")[0] ?? "";
        int level = -1;
        if (_kind == UpgradeKind.ExtraLevel && part.Split('|') is [var t, var l])
            (part, level) = (t, int.Parse(l, CultureInfo.InvariantCulture));
        try
        {
            (ResultSql, ResultDescription, ResultWhere) = await Task.Run(() => _kind switch
            {
                UpgradeKind.Aspiration => (Upgrades.BuildAspiration(_db, _ids, part, d!.Key, _modeFixed?.IsChecked == true ? "direct" : _modeShop?.IsChecked == true ? "conversion" : "both"), $"Added {partLabel.ToLowerInvariant()}", "Engine ▸ Engine parts & upgrades"),
                UpgradeKind.EngineSwap => (Upgrades.BuildEngineSwap(_db, _ids, d!.Key, price, mass), $"Added engine swap: {d.Title}", "Engine ▸ Engine swaps"),
                UpgradeKind.DrivetrainSwap => (Upgrades.BuildDrivetrainSwap(_db, _ids, d!.Key, drive, price, mass), $"Added drivetrain conversion: {d.Title}", "Drivetrain ▸ Drivetrain conversions"),
                UpgradeKind.TireCompound => (Upgrades.BuildTireCompound(_db, _ids, d!.Key, price), $"Added {d.Title.ToLowerInvariant()}","Tyres & grip ▸ Tyre compound & rim upgrades"),
                UpgradeKind.TireWidth => (Upgrades.BuildTireWidth(_db, _ids, useFront ? front : null, useRear ? rear : null, price), "Added wider tyres", "Tyres & grip ▸ Tyre width upgrades"),
                UpgradeKind.Spacers => shopMode
                    ? (Upgrades.BuildShopSpacers(_db, _stock, _ids, front, rear, price), "Added shop wheel spacers", "Tyres & grip ▸ Wheel spacers - shop upgrade")
                    : (Upgrades.BuildFixedSpacers(_stock, _ids, front, rear), "Set always-fitted wheel spacers", "Tyres & grip ▸ Wheel spacers - always fitted"),
                UpgradeKind.BodyPart => drive == "unlock_aero"
                    ? (Upgrades.UnlockAeroTuningForCar(_db, _ids), "Unlocked aero tuning", "Aerodynamics ▸ Wing & bumper downforce (List_AeroPhysics)")
                    : (Upgrades.BuildBodyPartRemoval(_db, _ids, drive, price, mass), $"Added {drive.Replace('_', ' ')} removal", "Aerodynamics ▸ Wing & bumper upgrades"),
                _ => (Upgrades.BuildExtraLevel(_db, _ids, part, level), $"Added {partLabel}", "the section that holds this part"),
            });
            DialogResult = true;
        }
        catch (Exception ex) when (ex is InvalidOperationException or IOException)
        {
            PreviewTxt.Text = "Could not add: " + ex.Message;
            PreviewTxt.Foreground = new SolidColorBrush(Color.FromRgb(0xFF, 0x3B, 0x30));
            AddBtn.IsEnabled = true;
        }
    }
}
