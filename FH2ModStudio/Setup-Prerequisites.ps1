# FH2 Mod Studio prerequisites: .NET 9 Desktop Runtime (the app itself), Python 3 + numpy (the car porter).
# Run by "Start FH2 Mod Studio.cmd" on first start (a marker file next to the exe remembers success; delete
# prerequisites.ok to check again). -CheckOnly reports without installing. Installs use winget when available,
# otherwise the official installers from Microsoft (aka.ms) and python.org, per user, no admin rights needed for Python.
# The Python that has numpy is written to python.txt; FH2 Mod Studio runs the porter with exactly that one (the "py"
# launcher and "python" can be different installations). Everything shown is also written to setup.log.
param([switch]$CheckOnly, [switch]$Launch)

# 'Stop' only for cmdlets: Windows PowerShell 5.1 turns a native program's stderr into a terminating error under
# 'Stop' when it is redirected, so "python -c 'import numpy'" on a PC without numpy aborted the whole setup
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$marker = Join-Path $here 'prerequisites.ok'
$pyFile = Join-Path $here 'python.txt'
$log = Join-Path $here 'setup.log'
$exe = Join-Path $here 'FH2ModStudio.exe'
$pythonUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
$dotnetUrl = 'https://aka.ms/dotnet/9.0/windowsdesktop-runtime-win-x64.exe'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Say($text, $color = 'Gray') {
    Write-Host $text -ForegroundColor $color
    try { Add-Content -Path $log -Value $text -Encoding UTF8 } catch { }
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($machine, $user | Where-Object { $_ }) -join ';'
}

function Has-Winget { [bool](Get-Command winget -ErrorAction SilentlyContinue) }

# runs a program, returns @(exit code, output text); never throws on stderr
function Run($file, [string[]]$arguments) {
    $out = & $file @arguments 2>&1 | ForEach-Object { "$_" }
    return @($LASTEXITCODE, ($out -join "`n"))
}

function Download-And-Run($url, $file, $arguments) {
    $path = Join-Path $env:TEMP $file
    Say "  downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $path -UseBasicParsing -ErrorAction Stop
    Say "  running $file"
    $p = Start-Process -FilePath $path -ArgumentList $arguments -Wait -PassThru -ErrorAction Stop
    Remove-Item $path -ErrorAction SilentlyContinue
    return $p.ExitCode
}

# ───────────── .NET 9 Desktop Runtime ─────────────
function Test-DotNet {
    $roots = @("$env:ProgramFiles\dotnet\shared\Microsoft.WindowsDesktop.App", "${env:ProgramFiles(x86)}\dotnet\shared\Microsoft.WindowsDesktop.App")
    foreach ($r in $roots) {
        if ($r -and (Test-Path $r)) {
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
# every real Python 3 on this PC (full paths), the py launcher's default first; the Microsoft Store stub is skipped
function Find-Pythons {
    $list = New-Object System.Collections.Generic.List[string]
    function Add-Py($p) { if ($p -and (Test-Path $p) -and $p -notlike '*\WindowsApps\*' -and -not $list.Contains($p)) { $list.Add($p) } }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $r = Run $launcher.Source @('-3', '-c', 'import sys; print(sys.executable)')
        if ($r[0] -eq 0) { Add-Py ($r[1].Trim() -split "`n")[-1].Trim() }
        $r = Run $launcher.Source @('-0p')
        if ($r[0] -eq 0) { foreach ($l in ($r[1] -split "`n")) { if ($l -match '([A-Za-z]:\\.+?python\.exe)') { Add-Py $Matches[1] } } }
    }
    foreach ($c in Get-Command python -All -ErrorAction SilentlyContinue) { Add-Py $c.Source }
    foreach ($d in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}", 'C:\')) {
        if ($d -and (Test-Path $d)) {
            Get-ChildItem $d -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
                Sort-Object { [int]($_.Name -replace '\D', '') } -Descending |
                ForEach-Object { Add-Py (Join-Path $_.FullName 'python.exe') }
        }
    }
    # only Python 3.9 - 3.14 (numpy has ready-made packages for these)
    return @($list | Where-Object {
        $r = Run $_ @('-c', 'import sys; print(sys.version_info[0] == 3 and 9 <= sys.version_info[1] <= 14)')
        $r[0] -eq 0 -and $r[1].Trim().EndsWith('True')
    })
}

function Has-Numpy($py) { (Run $py @('-c', 'import numpy'))[0] -eq 0 }

function Install-Numpy($py) {
    Say "Installing numpy for $py ..." 'Yellow'
    if ((Run $py @('-m', 'pip', '--version'))[0] -ne 0) {
        Say '  pip is missing - adding it'
        $r = Run $py @('-m', 'ensurepip', '--upgrade'); Say $r[1]
    }
    foreach ($extra in @(@('--user'), @())) {
        $r = Run $py (@('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location') + $extra + @('numpy'))
        Say $r[1]
        if (Has-Numpy $py) { return $true }
    }
    return $false
}

function Install-Python {
    Say 'Installing Python 3.12 for your user account...' 'Yellow'
    if (Has-Winget) {
        winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements | Out-Host
    }
    Refresh-Path
    if (-not (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
        $code = Download-And-Run $pythonUrl 'python-3.12-amd64.exe' '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1'
        if ($code -ne 0) { throw "Python installer exit code $code" }
    }
    Refresh-Path
}

# the Python FH2 Mod Studio will use: one that already has numpy, else the first one numpy installs into, else a fresh 3.12
function Ensure-PythonWithNumpy {
    $pys = Find-Pythons
    foreach ($p in $pys) { if (Has-Numpy $p) { Say "Python with numpy found: $p" 'Green'; return $p } }
    if ($pys.Count -gt 0) { Say ("Python found (" + ($pys -join ', ') + ") but numpy is missing.") 'Yellow' }
    else { Say 'No usable Python 3 (3.9 - 3.14) found.' 'Yellow' }
    if ($CheckOnly) { return $null }
    foreach ($p in $pys) { if (Install-Numpy $p) { Say "numpy installed for $p" 'Green'; return $p } }
    Install-Python
    foreach ($p in Find-Pythons) {
        if ((Has-Numpy $p) -or (Install-Numpy $p)) { Say "numpy ready for $p" 'Green'; return $p }
    }
    throw 'numpy could not be installed (see setup.log next to FH2ModStudio.exe).'
}

# ───────────── main ─────────────
try {
    Set-Content -Path $log -Value ("FH2 Mod Studio setup " + (Get-Date -Format s) + " on " + [Environment]::OSVersion.VersionString) -Encoding UTF8
    Say 'FH2 Mod Studio - checking what it needs' 'Cyan'
    $ok = $true
    if (Test-DotNet) { Say '.NET Desktop Runtime 9 found' 'Green' }
    elseif ($CheckOnly) { Say '.NET 9 Desktop Runtime is missing' 'Yellow'; $ok = $false }
    else { Install-DotNet; if (-not (Test-DotNet)) { throw '.NET 9 Desktop Runtime could not be installed' } }

    $py = Ensure-PythonWithNumpy
    if ($py) { Set-Content -Path $pyFile -Value $py -Encoding ASCII } else { $ok = $false }

    if ($ok -and -not $CheckOnly) {
        Set-Content -Path $marker -Value ("checked " + (Get-Date -Format s)) -Encoding UTF8
        Say 'Everything is ready.' 'Green'
    }
    if ($Launch) { Start-Process -FilePath $exe -WorkingDirectory $here }   # inherits the refreshed PATH
    if (-not $ok) { exit 1 }
}
catch {
    Say ("Setup failed: " + $_.Exception.Message) 'Red'
    Say 'You can install them by hand: .NET 9 Desktop Runtime (dotnet.microsoft.com) and Python 3.12 from python.org with "Add python.exe to PATH" ticked, then in a command prompt: py -m pip install numpy' 'Red'
    Say "Please send setup.log (next to FH2ModStudio.exe) when asking for help." 'Red'
    Read-Host 'Press Enter to close'
    exit 1
}
