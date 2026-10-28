param([string]$OutDir)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW6 {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
"@
[PW6]::SetProcessDPIAware() | Out-Null
$A = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$Cond = [System.Windows.Automation.PropertyCondition]
$proc = Get-Process FH2ModStudio
$root = $A::FromHandle($proc.MainWindowHandle)
function ById($el, $id) { $el.FindFirst($TS::Descendants, (New-Object $Cond($A::AutomationIdProperty, $id))) }
function Items($el) { $el.FindAll($TS::Children, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem))) }
function Shot($hwnd, $name) {
  $r = New-Object PW6+RECT
  [PW6]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  [PW6]::PrintWindow($hwnd, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)
  $bmp.Save("$OutDir\$name.png", [System.Drawing.Imaging.ImageFormat]::Png); "saved $name"
}
(ById $root "CarsTabBtn").GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Milliseconds 3000
(ById $root "SearchBox").GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("CorvetteZ06"); Start-Sleep -Milliseconds 600
(Items (ById $root "CarList"))[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 3000
$tp = (ById $root "KeepCheck").GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($tp.Current.ToggleState -eq "On") { $tp.Toggle() }
# open the dialog without blocking this script (ShowDialog is modal)
$btn = ById $root "AddUpgradeBtn"
$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Milliseconds 4000
$dlg = $A::RootElement.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade")))
if (-not $dlg) { $dlg = $root.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade"))) }
if (-not $dlg) { "dialog not found"; exit 1 }
$hwnd = [IntPtr]$dlg.Current.NativeWindowHandle
Shot $hwnd "add_dialog"
"preview: " + (ById $dlg "PreviewTxt").Current.Name
(ById $dlg "AddBtn").GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Milliseconds 5000
"status: " + (ById $root "StatusTxt").Current.Name
Shot $proc.MainWindowHandle "after_add"

