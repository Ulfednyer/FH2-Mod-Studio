param([string]$Search, [int]$Pick = 0, [string]$Out)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW2 {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
"@
[PW2]::SetProcessDPIAware() | Out-Null
$A = [System.Windows.Automation.AutomationElement]
$p = Get-Process FH2ModStudio
$root = $A::FromHandle($p.MainWindowHandle)
function Find($id) { $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty, $id))) }
$box = Find "SearchBox"
$vp = $box.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$vp.SetValue($Search)
Start-Sleep -Milliseconds 600
$list = Find "TableList"
$items = $list.FindAll([System.Windows.Automation.TreeScope]::Children, (New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem)))
"matches: $($items.Count)"
if ($items.Count -gt $Pick) { $items[$Pick].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() }
Start-Sleep -Milliseconds 1500; $t = Find "ScaleToggleBtn"; if ($t) { $t.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }; Start-Sleep -Milliseconds 1500
$r = New-Object PW2+RECT
[PW2]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc()
[PW2]::PrintWindow($p.MainWindowHandle, $dc, 2) | Out-Null
$g.ReleaseHdc($dc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
"saved"

