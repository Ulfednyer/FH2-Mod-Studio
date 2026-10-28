param([string]$OutDir)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW7 {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
"@
[PW7]::SetProcessDPIAware() | Out-Null
$A = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$Cond = [System.Windows.Automation.PropertyCondition]
$proc = Get-Process FH2ModStudio
$root = $A::FromHandle($proc.MainWindowHandle)
function ById($el, $id) { $el.FindFirst($TS::Descendants, (New-Object $Cond($A::AutomationIdProperty, $id))) }
function Items($el) { $el.FindAll($TS::Children, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem))) }
function Invoke($el) { $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
function Shot($hwnd, $name) {
  $r = New-Object PW7+RECT
  [PW7]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  [PW7]::PrintWindow($hwnd, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)
  $bmp.Save("$OutDir\$name.png", [System.Drawing.Imaging.ImageFormat]::Png); "saved $name"
}
Invoke (ById $root "CarsTabBtn"); Start-Sleep -Milliseconds 3000
(ById $root "SearchBox").GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("CorvetteZ06_15"); Start-Sleep -Milliseconds 800
(Items (ById $root "CarList"))[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 3000
$tp = (ById $root "KeepCheck").GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($tp.Current.ToggleState -eq "On") { $tp.Toggle() }
foreach ($case in @(@{Idx=3; Name="tyre"}, @{Idx=6; Name="level"})) {
  Invoke (ById $root "AddUpgradeBtn"); Start-Sleep -Milliseconds 3000
  $dlg = $A::RootElement.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade")))
  if (-not $dlg) { $dlg = $root.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade"))) }
  if (-not $dlg) { "dialog not found"; exit 1 }
  (Items (ById $dlg "KindList"))[$case.Idx].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
  Start-Sleep -Milliseconds 3000
  Shot ([IntPtr]$dlg.Current.NativeWindowHandle) ("dlg_" + $case.Name)
  "$($case.Name) preview: " + (ById $dlg "PreviewTxt").Current.Name
  Invoke (ById $dlg "AddBtn"); Start-Sleep -Milliseconds 5000
  "status: " + (ById $root "StatusTxt").Current.Name
}
Shot $proc.MainWindowHandle "after_add2"
