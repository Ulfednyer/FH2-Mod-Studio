# Forza Horizon 2 – game internals

Everything learned about Forza Horizon 2 while building FH2 Mod Studio, fh2sql.dll and the FH3 → FH2 car porter
(October 2026). The game is the **Xbox One build 1.0.0.64** (`forza_durango_release_final.exe`, image base
`0x140000000`) run on PC by **Azimuth 0.9.10**. Addresses below are absolute for that base; names like `sub_1412DCC80`
are IDA's. Deeper step-by-step detail lives in [`fh3port/README.md`](fh3port/README.md) (findings 1–14) and
[`fh3port/CRASHES.md`](fh3port/CRASHES.md).

Contents: [Running mods under Azimuth](#1-running-mods-under-azimuth) · [Files and archives](#2-files-and-archives) ·
[Game database](#3-game-database) · [String tables](#4-string-tables) · [Asset formats](#5-asset-formats-bundles) ·
[Rendering](#6-rendering-materials-and-shaders) · [Paint](#7-paint-manufacturer-colours-and-paint-groups) ·
[Physics](#8-physics) · [Upgrade shop](#9-upgrade-shop) · [Audio](#10-audio) · [UI data](#11-ui-thumbnails-logos-names) ·
[Graphics settings](#12-graphics-and-render-settings) · [Porter status](#13-fh3--fh2-car-porter-status) ·
[Other games](#14-other-forza-games) · [Crash reference](#15-crash-reference)

---

## 1. Running mods under Azimuth

- **The exe must never change on disk.** Azimuth checks its hash ("Game executable hash mismatch"). Every code change
  is made in memory by `fh2sql.dll`, injected into the Azimuth launcher before the game starts (FH2 Mod Studio does
  this; "Load mods automatically when Azimuth starts").
- **`Mount\hash.manifest` must not change either** – Azimuth refuses to start ("Incomplete or changed"). It is the
  game's index of every file (12-byte records: u64 hash of the lower-case Mount-relative path with backslashes – a
  double djb-style pass `h ^= c + (h >> 2) + (h << 5)`, seed 5381, low | high << 32 – plus a u32 per-file value; copying
  a sibling's works). A file not listed there does not exist for the game: new zips crashed it at `game+0xfd1927`.
  **Fix:** fh2sql.dll hooks the game's import `CreateFile2` (IAT RVA `0x1DD1148`, also CreateFileA/W,
  FindFirstFileExA, GetFileAttributesExA/W) and hands it `<game>\FH3Port\hash.manifest`, an extended copy. Without the
  DLL, the game crashes on start once added files are registered.
- **Replacing existing files works** without any of this (gamedbRC.slt, string tables, PhysicsSettings.ini, …).
- The translation layer runs the game's x64 code natively in the Azimuth process, so normal memory reads/writes and
  `VirtualProtect` work. fh2sql.dll's code hooks are call-site patches (4-byte rel32 change to a stub allocated within
  ±2 GB), never prologue rewrites.
- Logs and crash dumps: `amzimuth\data\logs\` (`azimuth.log` names the crash address `game+0x…`). The minidumps contain
  stacks and enough heap to read the objects involved (used to solve the collision crashes).
- **fh2sql.dll** (`dll/fh2sql.cpp`) features: named pipe `\\.\pipe\fh2sql` (frames: u32 length + UTF-8) that runs SQL on
  the live database with the game's own SQLite 3.6.19 functions (`g_pApp` `0x14354F4F8` + `0x40` → `CDatabase`, +`0x10`
  `sqlite3*`, +`0x18` its lock; prepare `0x14003D710`, step `0x14001EEE0`, …); `!info`; `#drift <lock> <speed>`; MSAA
  sample count (`0x1434B1DD8`, written before the renderer reads it); motion-blur keepers; the file hooks; the drift
  steering hook (§8.3). Settings in `fh2sql.ini` next to the DLL (written by FH2 Mod Studio).

## 2. Files and archives

- Game folder: `<game>\Mount\media\...`; paths in data look like `game:\media\cars\<car>.zip` (case-insensitive). A
  path's folder `X` may be a zip `X.zip` (e.g. `game:\Media\Stripped\RC0\Thumbnail_1.png` → `stripped\RC0.zip`).
- **Zips:** deflate, version 0x0A, time/date 0, a central-directory extra field `0x1123` (length 4 = absolute data
  offset), no local extra. `zipmanifest.xml` lists every zip; its dirsize = central directory size + 22. The porter
  writes zips in exactly this layout.
- Cars: `media\cars\<MediaName>.zip` (carbin, models, materials, textures, `physicsdefinition.bin`,
  `ManufacturerColors.bin`, `Lights.bin`, …). Shared library: `media\cars\_library\` (`Materials.zip`, `Textures.zip`,
  `scene\tires\tire_*.zip`, `scene\wheels\*.zip`), shaders in `media\_library\Shaders.zip`.
- Physics settings: `media\physics\PhysicsSettings.ini`, suspension geometries `media\physics\suspension\*.xml`.
- Database: `media\stripped\gamedbRC.slt`; string tables `media\stripped\stringtables\<LANG>.zip`; thumbnails and logos
  `media\stripped\RC*.zip`.

## 3. Game database

- `gamedbRC.slt` is a plain SQLite database. The game loads it into a memory VFS (journal off), so edits must go through
  the running process (fh2sql.dll's pipe) or into the file before the game starts. FH2 Mod Studio keeps edits as SQL
  "mods" re-applied on every start.
- The game's SQLite is **3.6.19**: no CTEs, no UPSERT; `INSERT … SELECT`, scalar sub-queries with `ORDER BY … LIMIT`,
  `COALESCE`, `CASE` work. Verify function identities against the 3.6.19 source order before calling them from a hook.
- Car rows: `Data_Car` (Id = car ordinal, `MediaName` = zip name), upgrade tables `List_Upgrade*` keyed by `Ordinal`
  (car) or by engine / drivetrain / body id; upgrade row ids follow `Id = key × 1000 + n`. Engine/body families
  (`List_UpgradeEngine`, `Data_Engine`, `Data_CarBody`, …) can be shared between cars – a ported car that shares an FH2
  engine id must not rewrite it.
- Make: `Data_Car.MakeID` → `List_CarMake`; `Data_Car.MakeName` must be the make's `DisplayName` exactly (a string id),
  otherwise the car sorts outside its make in the menus. Autoshow category: `Data_Car_Buckets.CarBucket` (FH3 ids mostly
  match; FH3 16/29 → FH2 21, 41 → 38; ids FH2 doesn't use break the menus).
- Spacers: `CarTrackOffsets` / `WheelNormOffsets` are loaded but never read (dead data). Track width that works:
  `Data_CarBody.ModelFront/RearTrackOuter`. A level-1 body upgrade pointing at a cloned `Data_CarBody` makes a buyable
  "spacer" upgrade.
- Suspension physics ids are `car × 1000 + level` (front) and `+100` (rear) in stock data.

## 4. String tables

- A string id is `_&N` with `N = (table hash16 << 16) | key`. Table hashes seen: `Data_Car` `0xCD49`, `List_CarMake`
  `0x3323`, `Upgrades` `0x7091`.
- `stringtables\<LANG>.zip` (18 languages: br, CHT, cz, DE, DEV, EN, ES, FR, GB, HU, IT, JP, KO, LOC, MX, nl, PL, RU)
  contains one `<Table>.str` per table. LSB2 format: 24-byte header (u32 @12 = section 0 offset, u32 @16 = section
  count, then the section offsets); section 0 = u32 size, u32 count, (count + 1) entries `(u16 key, u32 UTF-16 offset)`
  sorted with a `0xFFFF` sentinel, then the UTF-16 pool plus an extra null. **The game reads section 0 only** (reader
  `sub_141246F30`). `fh3port/strtables.py` parses and rebuilds these byte-identically.
- Menus outside the Autoshow show only string ids, so ported cars, new makes and new upgrade entries need real entries
  in every language (`fh3port.py names`, `fh3port.py upgrade-strings`).
- FH3's tables use 64-bit ids, keyed by their low 32 bits.

## 5. Asset formats (bundles)

All ForzaTech assets are **burG bundles**: a header, then tagged blobs (`Mesh`, `MatI`, `VLay`, `VerB`, `IndB`,
`MBuf`, `Skel`, `Mrph`, `Modl`, `MTPR`, `MNCL`, …) with per-blob version and metadata. FH2 reads bundle version 1.0;
FH3 writes 1.1 (20-byte header, count at +16). Each blob has two size fields – **they must both equal the real data
length** (a stale second size made the game read truncated layouts and crash D3D12 pipelines).

| Item | FH2 | FH3 | Notes |
|---|---|---|---|
| Mesh blob | 1.7 | 1.8 (+32 bytes) | header: i16 material, i16 bone/draw order, u16 LODFlags, u8 lastLOD, u8 firstLOD, u16 render pass |
| Modl | 1.1 | 1.2 (+u16) | u16 counts of meshes, buffers (VerB + IndB + MBuf + ConB + Skin), VLay, MatI must match the blobs |
| Skel | 0.0 | 1.0 (+u32) | |
| Material params (MTPR) | v2 | v3 | v3 adds a 16-byte GUID after the type byte; params are versioned individually |
| carbin model entries | v15 | v16 | v16 appends u32 n + n GUIDs |
| Manufacturer colours (MNCL) | 1.0, u16 masks | 1.1, u32 masks | |
| Textures (swatchbin) | 2.0 Durango tiled or "PC" path | BCXT v0.0 PC | FH2 loads FH3 PC textures natively through its non-2.0 path |

- **LOD flags:** bit 0 = LOD S, bit 1 = LOD0, bits 2–6 = LOD1–5. FH2 draws LOD S only in panel-open close-ups; FH3
  draws it for the player car. Render pass (u16 @8): `0x01` opaque, `0x04` transparent, `0x38` decal / alpha-test.
- **Vertices:** FH3 POSITION is RGBA16 SNORM × per-mesh scale + offset (w = normal.x), NORMAL RG16 SNORM (yz), TANGENT
  RGB10A2; FH2 uses RGB32F / RGBA16F / RGBA16F. Mesh binding = (buffer id, slot, stride, byte offset); draw = start
  index, base vertex, index count. VLays are addressed by **position**, buffers by **id**; the position-only layout
  (id −1) is always last.
- **Vertex layout must match a shader variant exactly.** Each shader's VDCL lists one input mask per render pass plus
  the full union; FH2 meshes always supply the full union. FH3 adds COLOR0 / TEXCOORD4 that FH2 never has. Invented UV
  channels need real UV transforms (mesh tail: 5 × offset.x, scale.x, offset.y, scale.y).
- Loader limits: at most ~10 VLay / ~25 buffers per model in FH2's own cars; `Model_LoadFromBundle` `0x1413F1D70`,
  `VertexLayout_ReadBlob` `0x1413F2CD0`, `Mesh_BindForDraw` `0x1413F4360`, `Blob_IsModelBuffer` `0x1413EEC50`.
- **carbin** (`CarScene::Scene::vf00` `0x1411AECB0`, model entry `CarRenderModel11::vf00` `0x1411ADEE0`): per model a
  material-override list (instance name + serialized material bundle – FH3 stores them as 1.1/v3, FH2 builds a null
  material from those → crash; `Car_ApplyNamedMaterialOverrides` `0x141189830`) and a paint-group list (§7).

## 6. Rendering, materials and shaders

- Material instances reference a shader (`*.shaderbin` in `Shaders.zip`, per-pass DXBC `.vso`/`.pso`) and parameters
  by **name hash**. FH2 and FH3 often use different names for the same input (light parameters, `F0a/F0b` vs FH3
  `F0aVector4`; FH3 `ColorColorParam` / `Gloss_floatVal` / `F0Vector4` → FH2 `DiffuseColorGroupColorParam` or
  `DiffuseColorA/B`, `GlossA/B`, `F0a/F0b`). The shader parameter reader `sub_1410C9920` accepts type bytes 0–9 and 11
  only; an unknown type leaves a null object.
- Parameter payloads (v2): Vector/Color/Swizzle/FunctionRange 16 bytes, Float/Bool/Int 4, Vector2 8, Texture = str7
  path + u32, Sampler 8, ColorGradient u32 n + 4n; 12-byte trailer.
- **Alpha-tested decals:** FH2 cuts out alpha-test (ATST) decals only in the depth pre-pass (`discard` in the
  ShadowDepth pixel shader); the colour pass relies on the depth match. A decal lying (nearly) coplanar with the paint
  therefore draws its transparent texels black. Decals must sit about 1 mm out (porter `zfight.py`; FH2's own overlays
  sit 0.5–2 mm above the body).
- Light functions: ids are identical in FH2 and FH3 (70 = Null). Lamp units need the full vertex layout, not AO.
- FH3-only shaders the porter remaps: `carpaint_standard_glossmask` → `carpaint_standard` with
  `CH1DiffuseTextureSwitchBool` (hash `0x7169AC81`) = 1. Still unmapped: `cf_outlinech1` (Corvette Z06 HE).

## 7. Paint: manufacturer colours and paint groups

- `ManufacturerColors.bin` holds an `MNCL` blob: u8 group count; per group u8 entry count; per entry mask, vec3 preview
  colour, str7 material path. A colour whose material FH2's library doesn't have renders **black**.
- FH3's library is layered: `Materials.zip` + `Materials_pri_44.zip` + `Materials_pri_45.zip` (higher `_pri_` wins; same
  for Textures); 76 paints exist only in the patch zips. Some FH3 paints and textures ship nowhere at all.
- **Paint groups:** each carbin model entry (v3+) has a list (material instance name → u32 group mask). Bits: 0 body,
  1 livery, 2 hood, 3 mirrors, 4 wing, 7 windows, 8–11 secondary, 12–15 two-tone (black by default in FH2) – same in FH2
  and FH3. Path: `Presentation11::CarPresentation::vf53` → `sub_1411B4A60` → `CarRenderModel11::off10_vf27`; table read
  by `sub_1411B0270`.

## 8. Physics

### 8.1 Collision (`physicsdefinition.bin`)

- Layout (versions 20–25): u32 1, u32 0, u32 Version, u32 DefinitionType, f32 Mass, 3×3 InertiaTensor, 3×3
  InverseInertiaTensor, vec3 HalfExtents, f32 BoundingRadius, vec3 GraphicsOffset, u32 NumChildren, vec3
  AabbCentreOffset, u32 NumCollisionShapes (@136), shapes (u32 type; types 2 convex hull / 5 point cloud: u32 size + raw
  blob; point cloud = header to 0x30 then count × vec4), then `ChildRenderModelIndices` (read when Version ≥ 13).
- The definition is deserialized into a **fixed 0x1000-byte arena** (`sub_1412DCC80`, allocator `sub_1412A6670` returns
  NULL when full → crash at `game+0x12dcda3`). FH2's own cars need at most 4048 bytes; FH3 cars with four 105-point
  clouds need ~7 KB. The porter thins point clouds by farthest-point sampling.
- `ChildRenderModelIndices` (`sub_1412DC2F0` → `sub_1412B0460`): u32 count, each entry indexes the definition list.
  All FH2 cars: 8 zero bytes. FH3 cars with count 4 and one definition crash at `game+0x12b04b3` – the porter clears it.

### 8.2 Car loading

- The car builder `sub_141056210` runs `SELECT * FROM Data_Car WHERE Id=…`, loads every installed upgrade row (43
  categories in registry order: 0 Engine, 1 Drivetrain, 2 CarBody, 3 Motor, 4 Brakes, **5 SpringDamper**, 6/7 anti-roll
  bars, 8 TireCompound, 9 RearWing, 10/11 rim sizes, 12–29 engine parts, 30–33 drivetrain parts, 34–41 body parts,
  42 motor parts; installed ids at `rbp+0x928` in its frame), then calls `sub_141061070` (damage defs + steering).
- `physicsdefinition.bin` is loaded per car by `sub_141056210` (fallback `nul_car_00`), with a 0x20000 file buffer.

### 8.3 Steering

- Steering is **per car**: `sub_1410622C0` copies `Data_Car.Steer*` (degrees, unconverted) to `car + 0x5C`: MaxAngle,
  MaxAngleFiltered, VelTurning, VelStraighten, Countersteer, DynFindPeak, AccelTimeToMaxRate, SpeedSensitive* …
  Forza Motorsport 7 instead has steering columns on the spring upgrade (drift suspension: 60°, speeds ×1.5, Ackermann
  0.15). fh2sql.dll points the builder's call at `0x141056DE3` to a stub and, when the installed SpringDamper id ends
  in 905 (FH2 Mod Studio's drift suspension), sets lock and speeds after the loader ran.

### 8.4 Tuning ranges

- `PhysicsSettings.ini` is loaded **twice**: `App::Initialize` binds `[CarTuning]` keys to the physics settings object
  (pointer `0x14365D6E8`; `TuneFinalDriveRatioMin` +608 … `TuneGasTankFillMax` +728; binder `sub_14104E390`) – this copy
  only drives the **tuning menu**. `App::vf00` loads the same values into a **static block at `0x14367AFD0`** (same
  order) that the **physics** uses.
- A tune is stored as a **0..1 slider position**; the applied value is `min + (max − min) × position` (camber:
  `sub_1412E3D20` reads `0x14367B018/1C`). Changing a range therefore also changes the real value of saved tunes.
  Live edits must write both copies.

### 8.5 Tyres and suspension

- Tyre compounds: `List_TireCompound` (FH2: 1–9, 20) with friction multi-curves, friction curves and affect curves
  (`List_TireFrictionMultiCurve`, `List_TireFrictionCurve`, `List_TireAffectCurve`); FH3's columns are a superset of FH2's,
  so FH3 compounds (`18_Drift`, `19_Drag`) import with re-numbered curves. Tyre models: `_library\scene\tires\tire_<name>.zip`.
- Suspension: `List_UpgradeSpringDamper` → front/rear `List_SpringDamperPhysics` (ride height, spring/damper ranges,
  StaticCamber/Toe/Caster, `SuspensionPhysicsTypeID` → geometry XML in `physics\suspension`, which only defines pivot
  points, no steering limits).

## 9. Upgrade shop

- The shop lists a part only when the `Upgrades` table names its (`UpgradeTypes.id`, `Level`) – or has a level −1
  wildcard for the type (shop SQL: `Upgrades.Level = PartTable.Level OR Upgrades.Level = -1`; views
  `View_UpgradeTypes`/`View_UpgradeParts` built from `CREATE VIEW` strings in the exe).
- Stock names: springs (type 13) levels 0–4 Stock / Street / Sport / Race / Rally; tyre compounds (21) 0–5 with
  4 = Drag, 5 = Rally; brakes (12) and anti-roll bars 0–3. Each level is one slot; tables hold one row per level and car.
- **Adding an entry:** rows at one fixed new level for every car + one `Upgrades` row (id, TypeId, IsException 0, Name,
  Level, Description, IconPath, ImagePath) whose Name / Description are `Upgrades.str` string ids with real text in every
  language. FH2 Mod Studio adds drift suspension (spring level 5, Upgrades 274), drift tyres (tyre level 6, Upgrades 275)
  and fills FH2's existing drag slot (tyre level 4).
- Tyre slot → compound in stock data: 1 street (5), 2 sport (6), 3 race (7), 5 rally (9).

## 10. Audio

- Engine sound: FH2 loads `audio\fmodanthem\durango\PG_<Data_Engine.MediaName>.bank` for every engine of the car
  (`Audio_GetCarEngineBankIds` `0x140292840`). A car whose engine name has no bank is silent – ported cars borrow the
  closest FH2 engine (same car's variant bank first, then cylinders / layout / aspiration / power).
- Banks: FH2 = FMOD Studio bank format **46** with **XMA** samples; FH3 = format **78** with **FADPCM** (plus `GS_`
  granular banks). FH2's FMOD can't load format 78. FH3 re-authored its car audio (the Huracán's FH3 bank shares no
  waveform GUIDs with FH2's), so FH3 sounds can only be transplanted by mapping FH3's instruments to FH2's RPM slots
  (open). Inspector: `research/fh3port/fmodbank.py`.

## 11. UI: thumbnails, logos, names

- Car thumbnails: `Data_Car.Thumbnail` (`game:\Media\Stripped\RC<n>\Thumbnail_<id>.png`); the files are swatchbins
  `Thumbnail_<id>_Big/_Small.swatchbin` (+ `B_<id>`) in that RC zip. FH3's path often names no RC zip or another id – the
  porter searches every RC zip and stores ported thumbnails in `stripped\RCFH3.zip`.
- Make logos: `List_CarMake.IconPath` / `IconPathLarge` (`Manu_Logo_<code>`, `L_Manu_Logo_<code>`). FH2's own rows for
  makes it never shipped (Holden, Chrysler, …) point at files that don't exist.
- FH3 car classes: `CarClasses` 0 D … 5 S2, 6 R, 7 X.

## 12. Graphics and render settings

- Render scenarios (`renderscenarios`, Global.xml) apply at scenario load; `FrameRate` (control +8, stock 60) scales
  motion blur – keep 120 when the game runs at 144 fps.
- Motion blur per camera: globals read every frame – driver `0x142E77558` (1.0), hood `0x142E77504` (0.6), bumper
  `0x142E774E4` (0.6); chase cameras share a read-only 1.0.
- MSAA sample count `0x1434B1DD8` (AppCommandLineParameters + 0x2608), read once when render targets are created.
- Live render objects found by vftable (FH2 Mod Studio `LiveSettings`): track settings (TrackPresentation11 + 0x8110),
  car LOD distances, crowd scale, shadow / windshield resolution, env-map frequency, mirror cars.
- `tracksettings.xml` is loaded, but its shadow/grass distances showed no visible effect.

## 13. FH3 → FH2 car porter: status

Pipeline per car (`fh3port/fh3port.py`, see its README): prepatch → ForzaToolsCli `fix-materials` → material map →
MTPR v3→v2 → light/param renames → geometry → carbin v16→v15 + paint groups + overrides → AO → LOD fixes → z-fight /
decal offsets → vertex layouts → textures → paint list → collision → plates → database rows (validated before and after
by `dbcheck.py`) → thumbnails, logos, tyres, library textures → names in all languages. Every run is snapshotted;
failures roll back; `undo` / `restore` work.

- ~290 FH3 cars ported and working, including the update/DLC cars (Porsche pack, Hoonigan, Hot Wheels, …) from a
  separate media folder (`fh3_extra`). Car zips can also be picked from anywhere.
- Known limits: engine sounds are borrowed FH2 banks; licence plates hidden by default (FH2 has no plate text);
  `cf_outlinech1` paint shader unmapped; five off-road cars keep their factory tyre in the drift-tyre slot.

## 14. Other Forza games

- [fmnext/cli](https://github.com/fmnext/cli) reads FM5–FM2023 and FH2–FH6. Version tables: carbin Scene v5 (FH2–FH4),
  v6 (FH5), v7 (FH6); CarRenderModel FH2 15, FH3/FH4 16, FH5 18, FH6 21; Mesh up to 1.12; Modl up to 1.4. FH4's car
  layout matches FH3's, so FH4 is the realistic next source; FH5/FH6 are not planned.
- The database supplied as "FH5" (`outputdbn.slt`, 837 cars, newest 2019) is Forza Motorsport 7: drag tyres = tyre
  level 4, compound 17 (group 8 Drag); drift suspension = spring level 5 with `DriftFront.xml` geometry, front camber
  −3, steering 60° ×1.5, Ackermann 0.15.

## 15. Crash reference

| Address | Cause | Fix |
|---|---|---|
| `game+0xfd1927` | added file not in hash.manifest | fh2sql.dll manifest redirect |
| `game+0x10c9b47` | FH3 v3 material params in models | `mtpr.py` |
| `game+0xfd841f` | Modl buffer counts ≠ blobs (incl. ConB/Skin) | `vlayfix.update_modl_counts` |
| D3D12 pipeline `E_INVALIDARG` | stale blob size → truncated vertex layout | `bundle.serialize` writes real sizes |
| `game+0x10d72bc` | carbin material override still 1.1/v3 | `carbin.convert_overrides` |
| `game+0x12dcda3` | collision > 4 KB arena | `physdef.py` thins point clouds |
| `game+0x12b04b3` | ChildRenderModelIndices with more entries than definitions | `physdef.py` clears the table |

Useful functions: zipmanifest loader `sub_140FD1600`, `IOSys::CMultiVolume::vf42` open `0x1411F49B0`, path hash
`sub_14126E0D0`, model loader `sub_1413F1D70`, mesh reader `sub_1413F13C0`, buffer reader `sub_1413F2140`, Lights.bin
`sub_1411ADD20`, texture reader `sub_1410DBB90`, pointer fix-up `sub_1413E6FF0`.
