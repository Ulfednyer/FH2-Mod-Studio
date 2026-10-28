using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;
using FH2ModStudio.Core;

namespace FH2ModStudio;

public partial class MainWindow : Window
{
    public ModSettings Settings { get; }
    public GameSession Session { get; }

    private static readonly Color Red = Color.FromRgb(0xFF, 0x3B, 0x30), RedText = Color.FromRgb(0xFF, 0x3B, 0x30);
    private static readonly Color Orange = Color.FromRgb(0xFF, 0x95, 0x00), OrangeText = Color.FromRgb(0xC9, 0x6F, 0x00);
    private static readonly Color Green = Color.FromRgb(0x34, 0xC7, 0x59), GreenText = Color.FromRgb(0x1E, 0x8E, 0x3E);
    private static readonly Color Grey = Color.FromRgb(0x8E, 0x8E, 0x93), GreyText = Color.FromRgb(0x63, 0x63, 0x66);

    public MainWindow()
    {
        InitializeComponent();
        Settings = ModSettings.Load();
        Session = new GameSession(Settings);
        Session.StatusChanged += OnStatus;
        HomePage.Init(this);
        CarsPage.Init(this);
        GraphicsPage.Init(this);
        DatabasePage.Init(this);
        PortPage.Init(this);
        OnStatus(Session.Status);
        SourceInitialized += (_, _) => { GlassHelper.EnableAcrylic(this); GlassHelper.FitMaximizeToWorkArea(this); };
        RestoreWindow();
        Loaded += (_, _) => { if (Settings.UiPage is { Length: > 0 } p && p != "home") ShowPage(p); };
        PreviewKeyDown += (_, e) =>
        {
            if (Keyboard.Modifiers != ModifierKeys.Control) return;
            var key = e.Key == Key.System ? e.SystemKey : e.Key;
            string? page = key switch
            {
                Key.D1 or Key.NumPad1 => "home", Key.D2 or Key.NumPad2 => "cars", Key.D3 or Key.NumPad3 => "graphics",
                Key.D4 or Key.NumPad4 => "database", Key.D5 or Key.NumPad5 => "port", _ => null,
            };
            if (page != null) { ShowPage(page); e.Handled = true; }
            else if (key == Key.F && CurrentPage()?.FindName("SearchBox") is TextBox search)
            {
                search.Focus();
                search.SelectAll();
                e.Handled = true;
            }
            else if (key == Key.S && CurrentPage()?.FindName("ApplyBtn") is Button { IsEnabled: true, IsVisible: true } apply)
            {
                apply.RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Primitives.ButtonBase.ClickEvent));
                e.Handled = true;
            }
        };
    }

    private FrameworkElement? CurrentPage() =>
        new FrameworkElement[] { HomePage, CarsPage, GraphicsPage, DatabasePage, PortPage }.FirstOrDefault(p => p.Visibility == Visibility.Visible);

    // ───────────── window size, position and page, kept between starts ─────────────

    private void RestoreWindow()
    {
        var s = Settings;
        if (s.UiWidth >= MinWidth && s.UiHeight >= MinHeight)
        {
            var r = new Rect(s.UiLeft, s.UiTop, s.UiWidth, s.UiHeight);
            var screen = new Rect(SystemParameters.VirtualScreenLeft, SystemParameters.VirtualScreenTop,
                                  SystemParameters.VirtualScreenWidth, SystemParameters.VirtualScreenHeight);
            if (screen.IntersectsWith(new Rect(r.Left + 40, r.Top, Math.Max(1, r.Width - 80), 40)))   // title bar reachable
            {
                WindowStartupLocation = WindowStartupLocation.Manual;
                Left = r.Left; Top = r.Top; Width = r.Width; Height = r.Height;
            }
        }
        if (s.UiMaximized) Loaded += (_, _) => WindowState = WindowState.Maximized;
    }

    private void SaveWindow()
    {
        var s = Settings;
        var r = WindowState == WindowState.Normal ? new Rect(Left, Top, Width, Height) : RestoreBounds;
        if (!r.IsEmpty) { s.UiLeft = r.Left; s.UiTop = r.Top; s.UiWidth = r.Width; s.UiHeight = r.Height; }
        s.UiMaximized = WindowState == WindowState.Maximized;
    }

    private static readonly SolidColorBrush StatusNormal = new(Color.FromRgb(0x48, 0x48, 0x4A));
    private static readonly SolidColorBrush StatusError = new(Color.FromRgb(0xD7, 0x00, 0x15));
    private static readonly string[] ErrorWords = { "could not", "couldn't", "failed", "error", "rejected", "not found", "not updated", "missing", "refused" };

    /// <summary>Status line: errors stand out in red; the full text and time are in the tooltip (long messages are cut).</summary>
    public void SetStatus(string text)
    {
        StatusTxt.Text = text;
        bool error = ErrorWords.Any(w => text.Contains(w, StringComparison.OrdinalIgnoreCase));
        StatusTxt.Foreground = error ? StatusError : StatusNormal;
        StatusTxt.FontWeight = error ? FontWeights.SemiBold : FontWeights.Normal;
        StatusTxt.ToolTip = $"{DateTime.Now:HH:mm:ss}  {text}";
    }

    public void ShowPage(string page)
    {
        if (Settings.UiPage != page) Settings.UiPage = page;
        HomePage.Visibility = page == "home" ? Visibility.Visible : Visibility.Collapsed;
        CarsPage.Visibility = page == "cars" ? Visibility.Visible : Visibility.Collapsed;
        GraphicsPage.Visibility = page == "graphics" ? Visibility.Visible : Visibility.Collapsed;
        DatabasePage.Visibility = page == "database" ? Visibility.Visible : Visibility.Collapsed;
        PortPage.Visibility = page == "port" ? Visibility.Visible : Visibility.Collapsed;
        var active = (Style)FindResource("SidebarIconBtnActive");
        var normal = (Style)FindResource("SidebarIconBtn");
        HomeTabBtn.Style = page == "home" ? active : normal;
        CarsTabBtn.Style = page == "cars" ? active : normal;
        GraphicsTabBtn.Style = page == "graphics" ? active : normal;
        DatabaseTabBtn.Style = page == "database" ? active : normal;
        PortTabBtn.Style = page == "port" ? active : normal;
        if (page == "database") DatabasePage.OnShown();
        if (page == "port") PortPage.OnShown();
        if (page == "graphics") GraphicsPage.OnShown();
        if (page == "cars") CarsPage.OnShown();
    }

    private void OnStatus(SessionStatus s)
    {
        switch (s.Game)
        {
            case GameState.NotRunning: Pill(GamePill, GameDot, GameTxt, Red, RedText, "Game not running"); break;
            case GameState.Launcher: Pill(GamePill, GameDot, GameTxt, Orange, OrangeText, "Azimuth launcher"); break;
            default: Pill(GamePill, GameDot, GameTxt, Green, GreenText, "In game"); break;
        }
        if (s.Game == GameState.NotRunning) Pill(ModsPill, ModsDot, ModsTxt, Grey, GreyText, "Mods idle");
        else if (s.ModsLoaded) Pill(ModsPill, ModsDot, ModsTxt, Green, GreenText, "Mods loaded");
        else Pill(ModsPill, ModsDot, ModsTxt, Red, RedText, "Mods not loaded");
        if (s.DatabaseReady) Pill(DbPill, DbDot, DbTxt, Green, GreenText, "Database ready");
        else Pill(DbPill, DbDot, DbTxt, Grey, GreyText, "Database offline");
        if (s.Message != null) SetStatus(s.Message);
        HomePage.OnStatus(s);
        CarsPage.OnStatus(s);
        DatabasePage.OnStatus(s);
        GraphicsPage.OnStatus(s);
        PortPage.OnStatus(s);
    }

    private static void Pill(Border pill, Ellipse dot, TextBlock text, Color c, Color textColor, string label)
    {
        var bg = new LinearGradientBrush(Color.FromArgb(0x25, c.R, c.G, c.B), Color.FromArgb(0x12, c.R, c.G, c.B), 90);
        var border = new LinearGradientBrush(Color.FromArgb(0x60, c.R, c.G, c.B), Color.FromArgb(0x25, c.R, c.G, c.B), 90);
        pill.Background = bg;
        pill.BorderBrush = border;
        dot.Fill = new SolidColorBrush(c);
        text.Foreground = new SolidColorBrush(textColor);
        text.Text = label;
    }

    private void HomeTab_Click(object sender, RoutedEventArgs e) => ShowPage("home");
    private void CarsTab_Click(object sender, RoutedEventArgs e) => ShowPage("cars");
    private void GraphicsTab_Click(object sender, RoutedEventArgs e) => ShowPage("graphics");
    private void DatabaseTab_Click(object sender, RoutedEventArgs e) => ShowPage("database");
    private void PortTab_Click(object sender, RoutedEventArgs e) => ShowPage("port");

    private void TitleBar_MouseDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ChangedButton != MouseButton.Left) return;
        if (e.ClickCount == 2) ToggleMaximize();
        else DragMove();
    }

    private void MinimizeBtn_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
    private void MaximizeBtn_Click(object sender, RoutedEventArgs e) => ToggleMaximize();
    private void CloseBtn_Click(object sender, RoutedEventArgs e) => Close();

    private void ToggleMaximize() => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void Window_StateChanged(object? sender, EventArgs e) =>
        RootBorder.Margin = new Thickness(0);   // maximized size = work area (GlassHelper.FitMaximizeToWorkArea), no overhang

    private void Window_Closed(object? sender, EventArgs e)
    {
        SaveWindow();
        Settings.Save();
        Session.Dispose();
    }
}
