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
        SourceInitialized += (_, _) => GlassHelper.EnableAcrylic(this);
        KeyDown += (_, e) =>
        {
            if (Keyboard.Modifiers != ModifierKeys.Control) return;
            if (e.Key == Key.D1) ShowPage("home");
            else if (e.Key == Key.D2) ShowPage("cars");
            else if (e.Key == Key.D3) ShowPage("graphics");
            else if (e.Key == Key.D4) ShowPage("database");
            else if (e.Key == Key.D5) ShowPage("port");
        };
    }

    public void SetStatus(string text) => StatusTxt.Text = text;

    public void ShowPage(string page)
    {
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
        RootBorder.Margin = WindowState == WindowState.Maximized ? new Thickness(7) : new Thickness(0);

    private void Window_Closed(object? sender, EventArgs e)
    {
        Settings.Save();
        Session.Dispose();
    }
}
