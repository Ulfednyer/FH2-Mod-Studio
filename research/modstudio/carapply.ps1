param([string]$OutDir)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW5 {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
"@
[PW5]::SetProcessDPIAware() | Out-Null
$A = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$Cond = [System.Windows.Automation.PropertyCondition]
$proc = Get-Process FH2ModStudio
$root = $A::FromHandle($proc.MainWindowHandle)
function ById($id) { $root.FindFirst($TS::Descendants, (New-Object $Cond($A::AutomationIdProperty, $id))) }
function Items($el) { $el.FindAll($TS::Children, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem))) }
function Shot($name) {
  $r = New-Object PW5+RECT
  [PW5]::GetWindowRect($proc.MainWindowHandle, [ref]$r) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  [PW5]::PrintWindow($proc.MainWindowHandle, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)
  $bmp.Save("$OutDir\$name.png", [System.Drawing.Imaging.ImageFormat]::Png); "saved $name"
}
(ById "CarsTabBtn").GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Milliseconds 3000
(ById "SearchBox").GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("4C"); Start-Sleep -Milliseconds 600
(Items (ById "CarList"))[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 3000
(Items (ById "SectionList"))[1].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 2500
$edit = (ById "EditorScroll").FindFirst($TS::Descendants, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)))
"torque before: " + $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("0.95"); Start-Sleep -Milliseconds 500
"bar: " + (ById "DirtyTxt").Current.Name
Shot "car_pending"
$keep = ById "KeepCheck"
$tp = $keep.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($tp.Current.ToggleState -eq "On") { $tp.Toggle() }
(ById "ApplyBtn").GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); Start-Sleep -Milliseconds 4000
"status: " + (ById "StatusTxt").Current.Name
"bar: " + (ById "DirtyTxt").Current.Name


