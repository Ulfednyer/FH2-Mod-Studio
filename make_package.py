"""Builds the shareable FH3 -> FH2 car porter package: dist\\FH3toFH2_CarPort_<date>.zip.

Contents (zip root = the folder friends put into their Forza Horizon 2 game folder):
  fh2sql\\FH2ModStudio\\        the app (Release build), launcher + prerequisite installer, fh2sql.dll
  fh2sql\\fh3port\\             the porter: scripts, name/parameter tables, docs, a blank fh3port.ini
  fh2sql\\research\\fh3port\\   the model check scripts the porter runs after each conversion
  fh2sql\\Forza Horizon 2 Convertor\\ForzaToolsCli.exe
  HOW TO USE.txt

Left out: everything personal or generated (FH2ModStudio settings, fh2sql.ini, debug logs, prerequisites.ok,
fh3port.ini paths, journal / ported-car lists, work\\, backups, __pycache__) and the Linux converter.
Run "dotnet build -c Release" in FH2ModStudio first.  usage: py make_package.py
"""
import fnmatch
import os
import sys
import zipfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "FH2ModStudio", "bin", "Release", "net9.0-windows", "win-x64")
ROOT = "FH3toFH2_CarPort"

APP_SKIP = ["FH2ModStudio.settings.json", "fh2sql.ini", "fh2sql_fs*.log", "fh2sql_fslog.enable", "prerequisites.ok",
            "*.pdb", "*.log"]
# researchh3port scripts the porter runs or imports (the rest are one-off investigations)
RESEARCH_FILES = ["strict.py", "modlcounts.py", "superset.py", "vdclgroups.py", "matidump.py"]
PORTER_FILES = ["*.py", "paramnames.json", "lightfunctions.json", "README.md", "CRASHES.md", "port_car.bat"]

INI = """[paths]
# Set these in FH2 Mod Studio (Port FH3 cars tab) - or here.
# game: the Forza Horizon 2 folder that contains Mount (default: two folders above this one)
# fh3: the Forza Horizon 3 installation folder (the one that contains media)
# fh3_extra: optional extra FH3 media folders (update / DLC trees), ';'-separated, searched before <fh3>\\media
# converter: ForzaToolsCli.exe (default: ..\\Forza Horizon 2 Convertor\\ForzaToolsCli.exe)
fh3 =
"""

GUIDE = """FH3 -> FH2 car porter
=====================

Converts Forza Horizon 3 cars (including DLC) into Forza Horizon 2 (PC, run with Azimuth).

What you need
- Forza Horizon 2 that runs with Azimuth.
- A Forza Horizon 3 PC installation (the cars are converted from your own copy).
- Windows 10/11. .NET 9 Desktop Runtime, Python 3 and numpy are installed automatically on first start.

Install
1. Unzip and put the "fh2sql" folder into your Forza Horizon 2 game folder
   (the folder that contains "Mount"), so you get <FH2>\\fh2sql\\FH2ModStudio, <FH2>\\fh2sql\\fh3port ...
2. Start "fh2sql\\FH2ModStudio\\Start FH2 Mod Studio.cmd" (not the .exe). The first start checks and installs
   .NET 9 Desktop Runtime, Python and numpy (Windows may ask for permission once), then opens FH2 Mod Studio.
3. In the "Port FH3 cars" tab (sidebar, 5th icon; Ctrl+5):
   - Forza Horizon 2 install location: your FH2 folder (found automatically if fh2sql is inside it)
   - Forza Horizon 3 install location: Browse... to your FH3 folder (the one that contains "media")
   - FH3 update / DLC media: only if you keep FH3 update/DLC files in a separate media folder; otherwise leave it.

Convert cars
- Pick cars in the list (search, filter "Not ported yet" / "Already in FH2 (replace)" / ...), Add, then
  "Convert & install". "Port all cars" does every car not yet in FH2. "Add zip file..." converts a car zip from
  anywhere (keep FH3's file name, e.g. por_918spyder_14.zip).
- Forza Horizon 2 must be closed while converting.
- Every car is checked after installing; a car that fails is rolled back and listed. "Undo this conversion"
  restores the state before the run. Original files are backed up in <FH2>\\FH3Port_Backup.

Playing
- ALWAYS start Forza Horizon 2 through FH2 Mod Studio: Home tab, "Start Azimuth" (keep "Load mods automatically
  when Azimuth starts" ticked). It loads fh2sql.dll, which the new cars need - without it the game crashes on start
  (it can't see the new files).
- Ported cars are in the Autoshow under their make.

Known limits
- Ported cars use a similar FH2 car's engine sound (FH3 sound banks can't be played by FH2).
- Licence plates are hidden by default (FH2 has no plate text); tick "Import licence plate" to keep them.

Details and troubleshooting: fh2sql\\fh3port\\README.md and CRASHES.md.
"""


def skip(name, patterns):
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns)


def main():
    if not os.path.exists(os.path.join(APP, "FH2ModStudio.exe")):
        sys.exit("build FH2 Mod Studio first: dotnet build -c Release (in FH2ModStudio)")
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", "%s_%s.zip" % (ROOT, date.today().strftime("%Y%m%d")))
    files = []
    for f in sorted(os.listdir(APP)):
        p = os.path.join(APP, f)
        if os.path.isfile(p) and not skip(f, APP_SKIP):
            files.append((p, "fh2sql/FH2ModStudio/" + f))
    port = os.path.join(HERE, "fh3port")
    for f in sorted(os.listdir(port)):
        if os.path.isfile(os.path.join(port, f)) and any(fnmatch.fnmatch(f, p) for p in PORTER_FILES):
            files.append((os.path.join(port, f), "fh2sql/fh3port/" + f))
    res = os.path.join(HERE, "research", "fh3port")
    for f in RESEARCH_FILES:
        files.append((os.path.join(res, f), "fh2sql/research/fh3port/" + f))
    conv = os.path.join(HERE, "Forza Horizon 2 Convertor")
    for f in ("ForzaToolsCli.exe", "README-RELEASE.txt"):
        if os.path.exists(os.path.join(conv, f)):
            files.append((os.path.join(conv, f), "fh2sql/Forza Horizon 2 Convertor/" + f))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, arc in files:
            z.write(src, ROOT + "/" + arc)
        z.writestr(ROOT + "/fh2sql/fh3port/fh3port.ini", INI)
        z.writestr(ROOT + "/fh2sql/fh3port/failed_cars.json", "{}\n")
        z.writestr(ROOT + "/HOW TO USE.txt", GUIDE.replace("\n", "\r\n"))
    print("%s: %d files, %.1f MB" % (out, len(files) + 3, os.path.getsize(out) / 2 ** 20))


if __name__ == "__main__":
    main()
