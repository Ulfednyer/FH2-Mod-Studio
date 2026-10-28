param([string]$Out)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PW3 {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
"@
[PW3]::SetProcessDPIAware() | Out-Null
$A = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]::Descendants
$p = Get-Process FH2ModStudio
$root = $A::FromHandle($p.MainWindowHandle)
function ById($id) { $root.FindFirst($TS, (New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty, $id))) }
function ByName($n) { $root.FindFirst($TS, (New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, $n))) }
function Invoke($el) { $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
function Text($id) { (ById $id).Current.Name }
function RunSql($sql) {
  (ById "SqlEditor").GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($sql)
  Invoke (ByName "Run   (Ctrl+Enter)")
  Start-Sleep -Milliseconds 1200
  "SQL> $sql`n   -> " + (Text "SqlMessage")
}
Invoke (ById "DatabaseTabBtn"); Start-Sleep -Milliseconds 800
(ById "SqlSeg").GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 500
RunSql "CREATE TEMP TABLE fh2undo(x); INSERT INTO fh2undo VALUES (1); INSERT INTO fh2undo VALUES (2);"
RunSql "UPDATE fh2undo SET x = x * 10 WHERE 1=1;"
RunSql "SELECT group_concat(x) AS vals FROM fh2undo;"
(ById "HistorySeg").GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 800
$undo = $root.FindAll($TS, (New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, "Undo")))
"undo buttons: $($undo.Count)"
Invoke $undo[0]; Start-Sleep -Milliseconds 1200
"status: " + (Text "StatusTxt")
$r = New-Object PW3+RECT
[PW3]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
[PW3]::PrintWindow($p.MainWindowHandle, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
(ById "SqlSeg").GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 400
RunSql "SELECT group_concat(x) AS vals FROM fh2undo;"
RunSql "DROP TABLE fh2undo;"
