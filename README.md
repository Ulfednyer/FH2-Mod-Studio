# FH2 Mod Studio

Tools for modding **Forza Horizon 2** (the Xbox One build, played on PC through the Azimuth translation layer):

- **FH2 Mod Studio** – a Windows app to launch the game with mods, edit any car (power, weight, gearing, suspension,
  grip, upgrades), change graphics settings beyond the menu, run SQL on the live game database, and port cars.
- **FH3 → FH2 car porter** (`fh3port`) – converts Forza Horizon 3 cars, including DLC and update cars, into Forza
  Horizon 2: models, materials, paints, textures, thumbnails, logos, collision, database rows and names in every
  language. About 290 FH3 cars have been ported and tested in game.
- **fh2sql.dll** – injected into the game by FH2 Mod Studio: makes added files visible to the game, runs SQL on the
  live database, applies MSAA / motion-blur settings, and gives the drift suspension its steering lock.
- **Drift & drag parts** – drift suspension, drift tyres and drag tyres for every car, and editable tuning-slider
  ranges (live and offline).

How the game works internally, and everything found while building these tools: **[game internals.md](game%20internals.md)**.

## Download

Get the newest ready-to-use version from **[Releases](../../releases)**: one zip with FH2 Mod Studio, the porter,
fh2sql.dll and the converter. Unzip it so that the `fh2sql` folder sits inside your Forza Horizon 2 game folder (the
folder that contains `Mount`), then start `fh2sql\FH2ModStudio\Start FH2 Mod Studio.cmd`. The first start installs
what is missing (.NET 9 Desktop Runtime, Python 3, numpy). `HOW TO USE.txt` in the zip has the details.

You need your own copies of the games: Forza Horizon 2 running with Azimuth, and a Forza Horizon 3 PC installation for
porting cars. No game files are included here.

Always start the game from FH2 Mod Studio (Home tab, "Start Azimuth") - ported cars need fh2sql.dll loaded.

## Repository layout

| Folder | Contents |
|---|---|
| `FH2ModStudio/` | The WPF app (.NET 9). `dotnet build -c Release` |
| `fh3port/` | The car porter (Python 3 + numpy). `README.md` there documents every step and finding; `CRASHES.md` every crash and its fix |
| `dll/` | `fh2sql.dll` source (C++). `build.ps1` builds it with Visual Studio's C++ tools and copies it to `fh2sql.dll` for the app |
| `research/` | Investigation scripts (IDA Python, format dumps, checks). Many are one-offs with paths from the original machine |
| `Forza Horizon 2 Convertor/` | Where `ForzaToolsCli.exe` goes (from the release zip; not in the source) |
| `make_package.py` | Builds the release zip (`dist/`) |

## Building

1. FH2 Mod Studio: .NET 9 SDK, `dotnet build -c Release` in `FH2ModStudio`.
2. fh2sql.dll: Visual Studio 2022+ with the C++ workload, then `powershell -File dll\build.ps1`.
3. Porter: Python 3.10+ and numpy; put `ForzaToolsCli.exe` (from a release) into `Forza Horizon 2 Convertor/`.
4. `py make_package.py` builds `dist/FH3toFH2_CarPort_<date>.zip`.

## Credits

- **[fmnext/cli](https://github.com/fmnext/cli)** (ForzaTech CLI Toolkit) and its `core` library – a reader for ForzaTech
  assets of FM5–FM2023 and FH2–FH6. Its bundle, mesh, model and car-scene readers and version tables were the reference
  for the porter's format work and for the planned FH4 support. All research archived in that project is the work of
  **[Doliman100](https://github.com/Doliman100)**.
- **ForzaTechStudio** – the C# format library the patched `ForzaToolsCli` converter is built from; also used as a format
  reference (manufacturer colours blob, bundles).
- **Azimuth** – the translation layer that runs Forza Horizon 2 on PC.

Forza, Forza Horizon and the Forza logo are trademarks of Microsoft Corporation. This project is not affiliated with or
endorsed by Microsoft or Playground Games. It contains no game files; you need your own copies of the games.
