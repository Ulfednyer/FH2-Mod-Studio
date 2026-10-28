param([string]$OutDir)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW8 {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
"@
[PW8]::SetProcessDPIAware() | Out-Null
$A = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$Cond = [System.Windows.Automation.PropertyCondition]
$CT = [System.Windows.Automation.ControlType]
$proc = Get-Process FH2ModStudio
$root = $A::FromHandle($proc.MainWindowHandle)
function ById($el, $id) { $el.FindFirst($TS::Descendants, (New-Object $Cond($A::AutomationIdProperty, $id))) }
function Items($el) { $el.FindAll($TS::Children, (New-Object $Cond($A::ControlTypeProperty, $CT::ListItem))) }
function Invoke($el) { $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
function Shot($hwnd, $name) {
  $r = New-Object PW8+RECT
  [PW8]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  [PW8]::PrintWindow($hwnd, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)
  $bmp.Save("$OutDir\$name.png", [System.Drawing.Imaging.ImageFormat]::Png)
}
function OpenSpacers() {
  Invoke (ById $root "AddUpgradeBtn"); Start-Sleep -Milliseconds 3000
  $d = $A::RootElement.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade")))
  if (-not $d) { $d = $root.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade"))) }
  (Items (ById $d "KindList"))[5].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
  Start-Sleep -Milliseconds 2500
  return $d
}
Invoke (ById $root "CarsTabBtn"); Start-Sleep -Milliseconds 2500
(ById $root "SearchBox").GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("CorvetteZ06_15"); Start-Sleep -Milliseconds 800
(Items (ById $root "CarList"))[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 3000
$tp = (ById $root "KeepCheck").GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($tp.Current.ToggleState -ne "On") { $tp.Toggle() }

# 1) shop mode, keep on
$dlg = OpenSpacers
$radios = $dlg.FindAll($TS::Descendants, (New-Object $Cond($A::ControlTypeProperty, $CT::RadioButton)))
"radios: " + (($radios | ForEach-Object { $_.Current.Name }) -join ", ")
($radios | Where-Object { $_.Current.Name -eq "Buy in the shop" }).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
Start-Sleep -Milliseconds 800
Shot ([IntPtr]$dlg.Current.NativeWindowHandle) "spacer_shop"
$edits = $dlg.FindAll($TS::Descendants, (New-Object $Cond($A::ControlTypeProperty, $CT::Edit)))
"shop fields: " + (($edits | ForEach-Object { $_.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value }) -join " / ")
"shop preview: " + (ById $dlg "PreviewTxt").Current.Name
Invoke (ById $dlg "AddBtn"); Start-Sleep -Milliseconds 5000
"status: " + (ById $root "StatusTxt").Current.Name

# 2) always-fitted mode, 0 mm (no change)
$dlg = OpenSpacers
Shot ([IntPtr]$dlg.Current.NativeWindowHandle) "spacer_fixed"
$edits = $dlg.FindAll($TS::Descendants, (New-Object $Cond($A::ControlTypeProperty, $CT::Edit)))
"fixed fields: " + (($edits | ForEach-Object { $_.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value }) -join " / ")
$edits[0].GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("0")
$edits[1].GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("0")
Start-Sleep -Milliseconds 500
"fixed preview: " + (ById $dlg "PreviewTxt").Current.Name
Invoke (ById $dlg "AddBtn"); Start-Sleep -Milliseconds 5000
"status: " + (ById $root "StatusTxt").Current.Name
