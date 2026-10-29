# Forza Horizon 1 (Xbox 360) -> Forza Horizon 2 (Xbox One / Azimuth): research and plan

Sources looked at (2026-10-29): FH1 post-release debug build (`D:\Xbox\Forza\fh1debug new extract`, `Forza2_PRF.xex`
in IDA on port 13339), the modded retail FH1 (`D:\Xbox\Forza\Forza Horizon`), the user's quickbms scripts
(`forza_horizon.bms`, `forza_motorsport*.bms`, `forza_minizip.bms`), ForzaTechStudio-Main, github.com/fmnext/cli.

## What exists already

| Tool | FH1 / FM4 (Xbox 360) | Useful for |
|---|---|---|
| ForzaTechStudio | No format support; conversion tool covers FM7 -> FH5, FH4 -> FM2023 (Xbox One era) | `Native\xcompress64.dll` + `CustomZipFile` (LZX zip entries) |
| fmnext/cli | No: FM5/6/7/2023 and FH2-FH6 only (README "Supported games") | FH2-side formats only |
| quickbms `forza_horizon.bms` | Zip with methods 0 / 8 / 13 / 15 / 21 (XMemDecompress) | confirms method 21 = XMem LZX |
| `forza_motorsport*.bms` | FM1/FM2-era CAB / SXWad archives | not needed for FH1 |
| `forza_minizip.bms` | FH3 PGZP minizip | not FH1 |

Nothing public converts FH1/FM4 car assets; the format work has to be done here (IDA has the FH1 reader code).

## FH1 formats (measured on AUD_R8GT_11)

- **Zips**: standard zip directory, entries method 21 = XMemCompress LZX stream. `research\fh1\fh1zip.py` reads them
  through `xcompress64.dll` (XMemDecompressStream), CRC-checked - all 57 entries of AUD_R8GT_11 OK.
- **Byte order**: big-endian everywhere (PowerPC).
- **Geometry**: `.carbin` version 5 (u32 BE `00000005`), but not FH2's scene format: `<car>_lod0.carbin` (4.2 MB)
  holds the whole car's meshes; `<car>.carbin` / `stripped_*.carbin` are lower LODs / stripped variants,
  `<car>_cockpit.carbin` the interior, `*_caliperXX_LOD0.carbin` / `*_rotorXX_LOD0.carbin` the brakes (version 1).
  Part names inside match FH2's naming: `bumperFa` / `bumperFrace`, `winga` / `wingrace`, `glassLHL`, `taillightL` ...
  -> FH2 upgradable parts (bumperf_a / bumperf_race ...). Loader: `.carbin` string xrefs in IDA
  (sub_830A27A0 car colour textures, sub_82EEF060, sub_84E2ECA0, sub_84E37A18; `.rmb.carbin` sub_82F07420).
- **Materials**: no materialbins. Named shader slots per mesh (`body`, `glass`, `chrome`, `carbon_fiber`,
  `grille1_alpha`, `rubber_trim`, `outer_rim` ...) with values in XML: `ShaderSettings.xml` (PaintScale,
  SpecularAmount/Power, FresnelIndex/Scalar, GlassColor ...), `ColorShaderSettings<n>.xml` per paint, shared
  `media\cars\shared\ShaderSettings\{Normal,Metallic,Matte,SLod}.xml`.
- **Textures**: `.xds` = Xbox 360 D3D texture: 52-byte big-endian header (GPU fetch constant: format, size, tiling)
  + tiled, 8-in-16 endian-swapped DXT data. Per car only a few atlases: `nodamage(_LOD0).xds` (2048^2),
  `damage`, `lights`, `damagelights`, `interior(_emissive)`, plus per-paint `BaseTexture` / `DamageTexture` rows
  in `Combo_Colors` (sub_830A27A0).
- **Database**: `Media\DB\gamedb.slt`, SQLite 3, 230 tables, 179 shared with FH2. Of 51 car tables 32 have identical
  columns, the rest differ by a few columns (FH2 adds RequiresGraphics, Height/Length/Wheelbase/Width, ShiftSystemID,
  UseProgressiveSpring ...; FH1 has OffRoad* scalars, IsRentable). Same lineage as FH2 -> the fh3port `Porter`
  (column mapping, donor values for missing columns, id remap, dbcheck) applies almost unchanged.
- **Other**: `CarAttribs.xml` (cockpit, gauges), `DigitalGauge\*.bgf/.bsg/.fbf/.XDS`, `LiveryMasks\*.tga`,
  `physicsdefinition.bin` (2.3 KB, version to check), `Physics\MAXData.xml`.

## Cars it would add

FH1 cars in neither FH2 (as installed now) nor FH3: 68 in the debug build, up to 41 more in the modded retail build
(FH1 DLC: `*_lce_*`, `*_hzn_*` ... - some retail extras may be FH2-Xbox-360 cars, to filter out). Examples:
Ascari KZ1R, Aston Martin Virage, Audi R8 GT / GT Spyder, Ferrari FXX / F40 Competizione / 458 Spider,
Koenigsegg CCXR, SSC Ultimate Aero, Gumpert Apollo S, Ruf RGT-8 / RT12R, Saleen S5S Raptor, Lamborghini
Reventon Roadster, Honda S2000 / Integra R / NSX-R GT, Mazda RX-8, VW Corrado, Lotus Elan Sprint, Mini Cooper S '65.

## Plan (each phase testable on its own)

1. **Read** - DONE 2026-10-29: `fh1zip.py` (zips) and `xds.py` (textures -> linear BCn / DDS / PNG preview).
   xds: header decoded (format, size, tiling, endian 8-in-16, mip count in fetch-constant dword 4 bits 6-9, mip
   address); untiling = XGAddress2DTiledOffset on 4x4 blocks, levels rounded to power-of-two and 32-block aligned;
   mips with short side <= 16 texels share one packed tile and are rebuilt from the last stored level (box filter +
   simple BC encoder) - sizes add up exactly (2048^2 DXT5: base 0x400000 + mips 0x15C000 + tail tile 0x4000).
   Checked: car atlas / gauge sheet / normal map previews look right, every stored mip matches its downscaled parent
   (mean error 2-12 vs 30-80 for a wrong offset), 330 textures of 24 debug + retail cars decode (DXT5 269, DXT1 40,
   DXN 21), 0 failures.
   Originally planned here: Next: an `xds.py` reader - parse the 52-byte header (format, width, height, mips,
   tiling flag), untile (Xenos 2D tiling, the XGUntileTextureLevel address formula) and swap 8-in-16 -> plain
   BC1/BC2/BC3/BC5. Check by writing DDS files and opening them. Low risk, well documented.
2. **Textures -> FH2** - DONE 2026-10-29 (not yet loaded in game): `swatch.py` writes the PC-layout swatchbin FH2
   loads linearly (BCXT 0.0 + HCXT header: GUID, size, mips, format id, sRGB at +2C/+30, mip list). It rebuilds 268 of
   268 FH2-loaded FH3-port textures byte for byte. FH1 -> FH2 format ids: DXT1 0, DXT3 1, DXT5 2, DXT5A 3, DXN 5,
   A8R8G8B8 13 (texels are B,G,R,A after the 8-in-32 swap). sRGB from the xds gamma sign bits. A whole FH1 car's 16
   textures convert and read back identical; FH2's tex.py check finds nothing to fix. Thumbnails: FH1
   `UI\Textures.zip Thumbnails\Thumbnail_<id>.xds` = one 768x288 A8R8G8B8 sheet with two views (3/4 front + side
   rotated 90 deg) - FH2 needs separate Big/Small/B_ thumbnails, so they will be cropped when cars are installed.
   Open: DXN channel order (360 ATI2 vs D3D11 BC5) - check on the first in-game normal map.
   Originally planned: write PC-layout swatchbins (FH2 reads FH3 PC BCXT v0.0 textures natively, fh3port tex.py /
   README) - the atlases become car textures under `Textures\`.
3. **Geometry reader** - DONE 2026-10-29: `carbin.py` reads FH1 / FM4 Xbox 360 `.carbin` files (v5 whole-car LOD0 and
   cockpit models, v1 caliper and rotor models). Decodes:
   - Parts hierarchy: 22 distinct car parts in LOD0 (`body`, `bumperFa`/`bumperFrace`, `bumperRa`, `winga`/`wingrace`,
     `skirtLa`/`skirtRa`, `trunk`, `undercarriagea`, `glass*`, `taillight*`, `exhaust*`, `wheel`), 23 parts in cockpit
     (`seatL`/`seatR`, `steering_wheel`, `cagerace`, `interior`, gauges, mirrors...).
   - Bounding boxes: tag 5 record with center (3f), min (-extent 3f), max (+extent 3f), 1.0 (float).
   - Meshes and shader slots: named material slots per mesh (`body`, `carbon_fiber`, `chrome`, `rubber_trim`,
     `plastic2`, `black`, `frame`, `detail_glass_red`, `weatherstrip`, `emblem`...).
   - Index buffers: triangle strips with restart markers (`0xFFFF` for 16-bit, `0x00FFFFFF` for 32-bit).
   - 28-byte vertex buffer:
       * bytes 0..4:   UV0 texture atlas UV (`USHORT2N` in [0, 1])
       * bytes 4..8:   UV1 livery / AO UV (`USHORT2N` in [0, 1])
       * bytes 8..16:  Position (`SHORT4N`, `xyz = center + q[:3] * extent` in meters)
       * bytes 16..20: Color / AO tint (`D3DCOLOR` 4x uint8)
       * bytes 20..28: QTangent (`SHORT4N` unit quaternion -> orthonormal unit Normal and Tangent)
   - Verified on `AUD_R8GT_11`: 113,328 vertices and 124,829 triangles across 22 parts; cockpit with 62,724 vertices
     and 71,969 triangles across 23 parts. Full 3D OBJ export (16.8 MB) and multi-view shaded PNG rendering verified.
4. **Geometry writer**: build FH2 per-part `.modelbin`s with fh3port's existing writers (`bundle.py`, `geom.py`
   layouts, `vlayfix` to the FH2 shader variants) and an FH2 scene `.carbin` (parts, upgradable parts by name:
   `bumperFa`/`bumperFrace` -> bumper part 34 rows, `winga`/`wingrace` -> wing 9 ...), skeleton from an FH2 donor
   car of similar size.
5. **Materials**: FH1 shader slot -> FH2 library material by name (`body` -> carpaint with paint groups, `glass` ->
   car glass, `chrome` -> chrome_polished, `carbon_fiber`, `rubber_trim` ...), atlas textures as DiffuseATexture,
   values from ShaderSettings.xml (same idea as matconv's name scoring + parameter renames).
6. **Database**: reuse `Porter` with FH1's gamedb as source (column map for the ~19 differing tables), engine sound
   borrowed from an FH2 engine as for FH3 cars.
7. **Wheels, brakes, physics, UI**: FH1 wheels/brakes carbins -> FH2 wheel modelbins (or FH2 donor rims first);
   physicsdefinition.bin version check (else donor + scale, see physdef.py); thumbnails from FH1 UI xds.
8. **Integrate** as a second source in the porter / FH2 Mod Studio "Port cars" page (source: FH1 folder).

Estimated effort: phases 1-2 small; 3-5 are the bulk (format reversing of carbin v5 and material mapping); 6-8 reuse
the FH3 porter. A first milestone worth testing in game: one FH1-only car with body geometry, atlas textures,
library materials and donor wheels.

## Forza Motorsport 4

FH1 was built on the FM4 engine, so the same formats are expected in FM4 (Xbox 360): LZX zips, carbin v5, xds,
ShaderSettings XML (to verify on FM4 files when available). Neither ForzaTechStudio nor fmnext/cli has anything on
FM4. A working FH1 reader would likely cover FM4 cars too.
