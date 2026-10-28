using System.Windows;
using System.Windows.Threading;

namespace FH2ModStudio;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnUnhandled;
        base.OnStartup(e);
    }

    private static void OnUnhandled(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        MessageBox.Show(e.Exception.Message, "FH2 Mod Studio - unexpected error", MessageBoxButton.OK, MessageBoxImage.Warning);
        e.Handled = true;
    }
}
