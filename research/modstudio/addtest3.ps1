param([string]$OutDir)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$Cond = [System.Windows.Automation.PropertyCondition]
$proc = Get-Process FH2ModStudio
$root = $A::FromHandle($proc.MainWindowHandle)
function ById($el, $id) { $el.FindFirst($TS::Descendants, (New-Object $Cond($A::AutomationIdProperty, $id))) }
function Items($el) { $el.FindAll($TS::Children, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem))) }
function Invoke($el) { $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
Invoke (ById $root "CarsTabBtn"); Start-Sleep -Milliseconds 2500
(ById $root "SearchBox").GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue("CorvetteZ06_15"); Start-Sleep -Milliseconds 800
(Items (ById $root "CarList"))[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 3000
$tp = (ById $root "KeepCheck").GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($tp.Current.ToggleState -eq "On") { $tp.Toggle() }
Invoke (ById $root "AddUpgradeBtn"); Start-Sleep -Milliseconds 3000
$dlg = $A::RootElement.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade")))
if (-not $dlg) { $dlg = $root.FindFirst($TS::Children, (New-Object $Cond($A::NameProperty, "Add upgrade"))) }
(Items (ById $dlg "KindList"))[6].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 3000
$combo = $dlg.FindFirst($TS::Descendants, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ComboBox)))
$combo.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand(); Start-Sleep -Milliseconds 800
$all = $combo.FindAll($TS::Descendants, (New-Object $Cond($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem)))
"options:"; foreach ($i in $all) { "  " + $i.Current.Name }
$pick = $all | Where-Object { $_.Current.Name -match "Spring" } | Select-Object -First 1
$pick.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 500
$combo.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse(); Start-Sleep -Milliseconds 500
"preview: " + (ById $dlg "PreviewTxt").Current.Name
Invoke (ById $dlg "AddBtn"); Start-Sleep -Milliseconds 5000
"status: " + (ById $root "StatusTxt").Current.Name
