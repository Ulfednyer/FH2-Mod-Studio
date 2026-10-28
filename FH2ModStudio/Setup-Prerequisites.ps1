# FH2 Mod Studio prerequisites: .NET 9 Desktop Runtime (the app itself), Python 3 on PATH + numpy (the car porter).
# Run by "Start FH2 Mod Studio.cmd" on first start (a marker file next to the exe remembers success; delete
# prerequisites.ok to check again). -CheckOnly reports without installing. Installs use winget when available,
# otherwise the official installers from Microsoft (aka.ms) and python.org, per user, no admin rights needed for Python.
param([switch]$CheckOnly, [switch]$Launch)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$marker = Join-Path $here 'prerequisites.ok'
$exe = Join-Path $here 'FH2ModStudio.exe'
$pythonUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
$dotnetUrl = 'https://aka.ms/dotnet/9.0/windowsdesktop-runtime-win-x64.exe'

function Say($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color }

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($machine, $user | Where-Object { $_ }) -join ';'
}

function Has-Winget { [bool](Get-Command winget -ErrorAction SilentlyContinue) }

function Download-And-Run($url, $file, $arguments) {
    $path = Join-Path $env:TEMP $file
    Say "  downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $path -UseBasicParsing
    Say "  running $file"
    $p = Start-Process -FilePath $path -ArgumentList $arguments -Wait -PassThru
    Remove-Item $path -ErrorAction SilentlyContinue
    return $p.ExitCode
}

# ───────────── .NET 9 Desktop Runtime ─────────────
function Test-DotNet {
    $roots = @("$env:ProgramFiles\dotnet\shared\Microsoft.WindowsDesktop.App")
    foreach ($r in $roots) {
        if (Test-Path $r) {
            if (Get-ChildItem $r -Directory | Where-Object { $_.Name -like '9.*' }) { return $true }
        }
    }
    return $false
}

function Install-DotNet {
    Say 'Installing the .NET 9 Desktop Runtime (Windows asks for permission)...' 'Yellow'
    if (Has-Winget) {
        winget install --id Microsoft.DotNet.DesktopRuntime.9 -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
    }
    if (-not (Test-DotNet)) {
        $code = Download-And-Run $dotnetUrl 'windowsdesktop-runtime-9-x64.exe' '/install /quiet /norestart'
        if ($code -ne 0 -and $code -ne 3010) { throw ".NET installer exit code $code" }
    }
}

# ───────────── Python 3 + numpy ─────────────
function Find-PythonExe {
    foreach ($name in 'py', 'python') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike '*WindowsApps*') {
            try {
                $v = & $cmd.Source -c "import sys; print(sys.version_info[0])" 2>$null
                if ($v -eq '3') { return $cmd.Source }
            } catch { }
        }
    }
    return $null
}

function Find-PythonInstall {
    # installed but not on PATH: the usual install folders, newest first
    $dirs = @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}", 'C:\')
    $found = foreach ($d in $dirs) {
        if (Test-Path $d) { Get-ChildItem $d -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue }
    }
    $found | Where-Object { Test-Path (Join-Path $_.FullName 'python.exe') } |
        Sort-Object { [int]($_.Name -replace '\D', '') } -Descending | Select-Object -First 1
}

function Add-ToUserPath($dirs) {
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($user -split ';' | Where-Object { $_ })
    $added = $false
    foreach ($d in $dirs) {
        if ($parts -notcontains $d) { $parts = @($d) + $parts; $added = $true }
    }
    if ($added) {
        [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
        Say "  added to your PATH: $($dirs -join ', ')" 'Green'
    }
    Refresh-Path
}

function Ensure-Python {
    $py = Find-PythonExe
    if ($py) { Say "Python found: $py" 'Green'; return $py }
    $inst = Find-PythonInstall
    if ($inst) {
        Say "Python is installed ($($inst.FullName)) but not on PATH." 'Yellow'
        if ($CheckOnly) { return $null }
        Add-ToUserPath @($inst.FullName, (Join-Path $inst.FullName 'Scripts'))
        $py = Find-PythonExe
        if ($py) { return $py }
        return (Join-Path $inst.FullName 'python.exe')
    }
    Say 'Python 3 is not installed.' 'Yellow'
    if ($CheckOnly) { return $null }
    Say 'Installing Python 3.12 for your user account...' 'Yellow'
    if (Has-Winget) {
        winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements | Out-Host
    }
    Refresh-Path
    if (-not (Find-PythonExe)) {
        $code = Download-And-Run $pythonUrl 'python-3.12-amd64.exe' '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1'
        if ($code -ne 0) { throw "Python installer exit code $code" }
    }
    Refresh-Path
    $py = Find-PythonExe
    if (-not $py) {
        $inst = Find-PythonInstall
        if ($inst) { Add-ToUserPath @($inst.FullName, (Join-Path $inst.FullName 'Scripts')); $py = Find-PythonExe }
    }
    if (-not $py) { throw 'Python was installed but cannot be started - restart Windows and try again.' }
    return $py
}

function Ensure-Numpy($py) {
    & $py -c "import numpy" 2>$null
    if ($LASTEXITCODE -eq 0) { Say 'numpy found' 'Green'; return $true }
    Say 'numpy is missing.' 'Yellow'
    if ($CheckOnly) { return $false }
    Say 'Installing numpy...' 'Yellow'
    & $py -m pip install --user --disable-pip-version-check numpy | Out-Host
    & $py -c "import numpy" 2>$null
    return ($LASTEXITCODE -eq 0)
}

# ───────────── main ─────────────
try {
    Say 'FH2 Mod Studio - checking what it needs' 'Cyan'
    $ok = $true
    if (Test-DotNet) { Say '.NET 9 Desktop Runtime found' 'Green' }
    elseif ($CheckOnly) { Say '.NET 9 Desktop Runtime is missing' 'Yellow'; $ok = $false }
    else { Install-DotNet; if (-not (Test-DotNet)) { throw '.NET 9 Desktop Runtime could not be installed' } }

    $py = Ensure-Python
    if (-not $py) { $ok = $false }
    elseif (-not (Ensure-Numpy $py)) { $ok = $false }

    if ($ok -and -not $CheckOnly) {
        Set-Content -Path $marker -Value ("checked " + (Get-Date -Format s)) -Encoding UTF8
        Say 'Everything is ready.' 'Green'
    }
    if ($Launch) { Start-Process -FilePath $exe -WorkingDirectory $here }   # inherits the refreshed PATH
    if (-not $ok) { exit 1 }
}
catch {
    Say ("Setup failed: " + $_.Exception.Message) 'Red'
    Say 'You can install them by hand: .NET 9 Desktop Runtime (dotnet.microsoft.com) and Python 3 from python.org with "Add python.exe to PATH" ticked, then: py -m pip install numpy' 'Red'
    Read-Host 'Press Enter to close'
    exit 1
}
