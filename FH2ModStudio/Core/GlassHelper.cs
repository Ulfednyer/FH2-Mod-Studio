using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace FH2ModStudio.Core;

/// <summary>Windows 11 acrylic backdrop, Windows 10 blur-behind fallback (same as xInput Macro Tool).</summary>
public static class GlassHelper
{
    private const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
    private const int DWMSBT_TRANSIENTWINDOW = 3;
    private const int WCA_ACCENT_POLICY = 19;
    private const int ACCENT_ENABLE_BLURBEHIND = 3;

    [StructLayout(LayoutKind.Sequential)]
    private struct AccentPolicy
    {
        public int AccentState;
        public int AccentFlags;
        public uint GradientColor;
        public int AnimationId;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WindowCompositionAttributeData
    {
        public int Attribute;
        public IntPtr Data;
        public int SizeOfData;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MARGINS
    {
        public int Left, Right, Top, Bottom;
    }

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    [DllImport("dwmapi.dll")]
    private static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref MARGINS margins);

    [DllImport("user32.dll")]
    private static extern int SetWindowCompositionAttribute(IntPtr hwnd, ref WindowCompositionAttributeData data);

    /// <summary>The windows are normal (not layered: AllowsTransparency="False") with the DWM frame extended over the
    /// whole client area (WindowChrome GlassFrameThickness -1); WPF clears to transparent so the blur shows through.
    /// Layered windows made WPF re-render the whole window on the CPU for every pixel of a drag - that was the lag.</summary>
    // ───────────── maximize to the monitor's work area (not under the taskbar) ─────────────

    private const int WM_GETMINMAXINFO = 0x0024;

    [StructLayout(LayoutKind.Sequential)] private struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] private struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct MINMAXINFO { public POINT Reserved, MaxSize, MaxPosition, MinTrackSize, MaxTrackSize; }
    [StructLayout(LayoutKind.Sequential)] private struct MONITORINFO { public int Size; public RECT Monitor, Work; public uint Flags; }

    [DllImport("user32.dll")] private static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);
    [DllImport("user32.dll")] private static extern bool GetMonitorInfo(IntPtr monitor, ref MONITORINFO info);

    /// <summary>A borderless window maximizes over the whole monitor, taskbar included; this keeps it to the work area
    /// of whichever monitor it is on.</summary>
    public static void FitMaximizeToWorkArea(Window window)
    {
        var source = HwndSource.FromHwnd(new WindowInteropHelper(window).Handle);
        source?.AddHook((IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled) =>
        {
            if (msg != WM_GETMINMAXINFO) return IntPtr.Zero;
            var monitor = MonitorFromWindow(hwnd, 2 /* MONITOR_DEFAULTTONEAREST */);
            var info = new MONITORINFO { Size = Marshal.SizeOf<MONITORINFO>() };
            if (monitor == IntPtr.Zero || !GetMonitorInfo(monitor, ref info)) return IntPtr.Zero;
            var mmi = Marshal.PtrToStructure<MINMAXINFO>(lParam);
            mmi.MaxPosition.X = info.Work.Left - info.Monitor.Left;
            mmi.MaxPosition.Y = info.Work.Top - info.Monitor.Top;
            mmi.MaxSize.X = info.Work.Right - info.Work.Left;
            mmi.MaxSize.Y = info.Work.Bottom - info.Work.Top;
            Marshal.StructureToPtr(mmi, lParam, true);
            handled = true;
            return IntPtr.Zero;
        });
    }

    public static void EnableAcrylic(Window window)
    {
        var hwnd = new WindowInteropHelper(window).Handle;
        if (HwndSource.FromHwnd(hwnd)?.CompositionTarget is { } target) target.BackgroundColor = System.Windows.Media.Colors.Transparent;
        if (Environment.OSVersion.Version >= new Version(10, 0, 22000))
        {
            int backdrop = DWMSBT_TRANSIENTWINDOW;
            DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ref backdrop, sizeof(int));
            var margins = new MARGINS { Left = -1, Right = -1, Top = -1, Bottom = -1 };
            DwmExtendFrameIntoClientArea(hwnd, ref margins);
            return;
        }
        var accent = new AccentPolicy { AccentState = ACCENT_ENABLE_BLURBEHIND, AccentFlags = 2, GradientColor = 0x99000000 };
        int size = Marshal.SizeOf(accent);
        var ptr = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(accent, ptr, false);
            var data = new WindowCompositionAttributeData { Attribute = WCA_ACCENT_POLICY, Data = ptr, SizeOfData = size };
            SetWindowCompositionAttribute(hwnd, ref data);
        }
        finally
        {
            Marshal.FreeHGlobal(ptr);
        }
    }
}
