@echo off
rem Ports FH3 cars into FH2 with fh3port (same pipeline as the working NSX) and checks the result.
rem   port_car.bat                       ports the Lamborghini Centenario (LAM_Bellissima_17)
rem   port_car.bat LAM_Bellissima_17 ACU_NSX_16 ...   ports the given cars (FH3 MediaNames)
rem Already ported cars stay installed; undo everything with:  py fh3port.py restore
rem Set NOPAUSE=1 to skip the final pause (for running from another script).
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title fh3port

set "CARS=%*"
if "%CARS%"=="" set "CARS=LAM_Bellissima_17"

set "PY=py"
where py >nul 2>&1 || set "PY=python"
where %PY% >nul 2>&1 || (echo Python not found - install Python 3.11+ and numpy. & goto :fail)

tasklist /FI "IMAGENAME eq azimuth.exe" /NH | find /I "azimuth.exe" >nul
if not errorlevel 1 (
    echo Forza Horizon 2 ^(azimuth.exe^) is running. Close it first, then run this again.
    goto :fail
)

echo === Checking setup
%PY% -I fh3port.py setup | find /I "setup ok" >nul || (%PY% -I fh3port.py setup & goto :fail)

rem fh3port works on a copy of the current database, so cars ported earlier stay installed
echo === Porting: %CARS%
%PY% -I fh3port.py port %CARS% > "work\port_last.log" 2>&1
set "RC=%ERRORLEVEL%"
type "work\port_last.log"
if not "%RC%"=="0" goto :fail
findstr /C:"convert FAILED" "work\port_last.log" >nul && goto :fail

echo.
echo === Verifying
set "BAD=0"
for %%c in (%CARS%) do (
    %PY% -I verify.py %%c > "work\verify_%%c.log" 2>&1
    findstr /C:"problems: 0" "work\verify_%%c.log" >nul && (echo %%c: verify ok) || (echo %%c: verify FAILED - see work\verify_%%c.log & set "BAD=1")
)
if "!BAD!"=="1" goto :fail

echo.
echo Done. Start the game through FH2 Mod Studio or ..\start.bat ^(fh2sql.dll must be injected^).
if not defined NOPAUSE pause
exit /b 0

:fail
echo.
echo Port did not complete.
if not defined NOPAUSE pause
exit /b 1
