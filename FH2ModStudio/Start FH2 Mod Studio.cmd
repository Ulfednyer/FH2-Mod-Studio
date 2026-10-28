@echo off
rem Starts FH2 Mod Studio. On the first start it checks and installs what it needs (.NET 9 Desktop Runtime,
rem Python 3 on PATH, numpy); after that prerequisites.ok makes it start straight away. Delete that file to check again.
cd /d "%~dp0"
if exist "prerequisites.ok" if exist "FH2ModStudio.exe" (
    start "" "FH2ModStudio.exe"
    exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Prerequisites.ps1" -Launch
