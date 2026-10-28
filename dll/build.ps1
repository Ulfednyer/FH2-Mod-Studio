$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ tools not found' }
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
cmd /c "`"$vcvars`" >nul && cl /nologo /O2 /EHsc /std:c++17 /W4 /MT /LD fh2sql.cpp /Fe:fh2sql.dll /link /NOLOGO"
if ($LASTEXITCODE) { throw "cl failed ($LASTEXITCODE)" }
Remove-Item fh2sql.obj, fh2sql.exp, fh2sql.lib -ErrorAction SilentlyContinue
# FH2 Mod Studio ships ..\fh2sql.dll (FH2ModStudio.csproj); the previous one is kept as ..\fh2sql.prev.dll
$dest = Join-Path (Split-Path $PSScriptRoot) 'fh2sql.dll'
if (Test-Path $dest) { Copy-Item $dest (Join-Path (Split-Path $PSScriptRoot) 'fh2sql.prev.dll') -Force }
Copy-Item fh2sql.dll $dest -Force
"built $PSScriptRoot\fh2sql.dll -> $dest"
