# FH3 → FH2 car port — tools, findings and status

Porting Forza Horizon 3 cars (`C:\Games\Forza Horizon 3`, PC/UWP build) into Forza Horizon 2 (Xbox One build run on
PC by Azimuth 0.9.10, game folder `Anthem_1.0.0.64_x64__8wekyb3d8bbwe\Mount`).
Last updated 2026-10-20.

## Status at a glance

| Stage | Status |
|---|---|
| Database port (Data_Car + all car/engine/drivetrain/body/physics rows, names, price) | **Works** – NSX shows in the Autoshow with name, logo, class S1 831, AWD, stats, 196,000 CR |
| zipmanifest registration | **Works** (converter's `manifest-line`, FH2-native zip layout) |
| New files visible to the game (hash.manifest) | **Works** – needs `fh2sql.dll` injected on every launch (Mod Studio does it) |
| Material parameters (crash on select) | **Fixed** – `mtpr.py` |
| Geometry: tyres | **Works** – correct size/position in game |
| Car body (carbin) | **Works** (user-tested 2026-10-19) – `carbin.py` (FH3 model entries v16 → FH2 v15) |
| Thumbnails | **Work** (user-tested) – `tex.py` |
| Paint / body | **Works** (user-tested 2026-10-19) – `geom.py` drops FH3's COLOR0/TEXCOORD4; `mncl.py` paint list |
| Interior | **Mostly works** (user-tested 2026-10-19 after `matmap.py`) |
| Headlights / taillights | **Light up** (user-tested 2026-10-20) – `lightparams.py` renames FH3 light parameters to FH2's |
| Grilles (honeycomb) | **Work** (user-tested 2026-10-20) – `slod.py`: grilles every LOD |
| Intake panels / intercooler look, missing textures | **Fixed** (installed 2026-10-20; rear bumper still being compared with FH3) – porter now copies all 121 library textures the materials reference (was 7) |
| Taillight flicker (z-fighting) | **Fixed** (user-tested 2026-10-20) – `zfight.py` moves opaque parts 1 mm off coplanar glass overlays |
| Engine sound | **Works** (user-tested 2026-10-25) – borrowed from a matching FH2 engine (`fix_engine_audio`, finding 9) |
| Second car (Lamborghini Centenario, `LAM_Bellissima_17`) | **Works** (user-tested 2026-10-25) – ported with `port_car.bat` |
| Batch port of all cars | Ready to try car by car (`port_car.bat <MediaName>...`) |

Current game state: the **Acura NSX '17 pilot is installed** (re-ported 2026-10-20 with all fixes). It is drivable,
used by the AI in championships. Undo everything with `py fh3port.py restore`.

## Tools in this folder

| File | Purpose |
|---|---|
| `port_car.bat` | One-click port: `port_car.bat [MediaName…]` (default `LAM_Bellissima_17`, the Centenario), setup check, port, verify |
| `CRASHES.md` | Every crash of the NSX pilot, its cause and fix, attempts that didn't help, rules for ported models |
| `fh3port.py` | Main porter. `plan` (what happens to each FH3 car), `port <MediaName…|all>`, `restore`, `status` |
| `verify.py` | Checks every touched zip (layout, CRC, manifest), physics files, database integrity, per-car rows |
| `mtpr.py` | Material parameter reader/writer. `check <zip>`, `fix <in> <out>`; run automatically by the porter |
| `geom.py` | Geometry converter (vertex re-encoding, Mesh/Modl/Skel downgrade). `fix <in> <out>`; run automatically |
| `carbin.py` | Carbin parser mirroring FH2's reader + FH3→FH2 downgrade. `check <carbin|zip>…`, `fix <in> <out>`; run automatically |
| `tex.py` | Texture fix-ups (UI cube flag, BC sizes). `check <zip>…`, `fix <in.zip> <out.zip>`; run automatically |
| `mncl.py` | Paint list (`ManufacturerColors.bin`) MNCL 1.1 → 1.0. `fix <in.zip> <out.zip>`; run automatically |
| `slod.py` | LOD fix-ups: sibling-less exterior `__SLOD` models (grilles) → every LOD, other exterior `__SLOD` → S..LOD1, radiosity overlay meshes hidden; run automatically |
| `vlayfix.py` | Rebuilds vertex layouts/buffers so every mesh exactly matches a compiled variant (VDCL) of its FH2 shader; run automatically |
| `bundle.py` | Full burG 1.0 reader/writer (adds/removes blobs); reproduces FH2 modelbins byte for byte (`py bundle.py test <zip>`) |
| `aofix.py` | Fills empty carbin AO maps of drawn models (not bulbs/glass/lenses/interior LOD) with a white BC4 AO built from the car's own AO texture; run automatically |
| `zfight.py` | Z-fighting: opaque meshes within 0.3 mm of glass move 1 mm off it; stacked opaque layers (>=20 % of triangles within 0.5 mm) move 1 mm forward; locally coplanar strips (>=8 triangles) move just those vertices 1 mm out; run automatically |
| `lightparams.py` | Renames FH3 parameter names to FH2's per resolved shader: light id/colour/mask table + generic type-suffix matches (`F0aVector4`→`F0a`) using `paramnames.json`; run automatically |
| `paramnames.json` | Parameter hash → name table extracted from ForzaTechStudio's `NameHashService.cs` (2,072 names) |
| `matmap.py` | Replaces materials the converter remapped to a guessed FH2 shader with FH2 library materials (table `MAP`); run automatically |
| `probe.py` | Registers a tiny test zip (used to prove the hash.manifest mechanism) |
| `plan.txt` | Output of `fh3port.py plan` |
| `work\` | Converted zips, reports, database working copy |
| `..\research\` | Every analysis script of this investigation (see bottom) |

Pipeline per car (`fh3port.py port`):
1. `ForzaToolsCli fix-materials` (converter) → materials bundled/remapped, swatchbin containers 1.1→1.0.
2. `mtpr.fix_zip` → FH3 v3 material parameters inside modelbins rewritten as FH2 v2.
3. `geom.fix_zip` → FH3 geometry re-encoded for FH2; `carbin.fix_zip` → carbin downgraded; `tex.fix_zip` → texture
   header fix-ups (also applied to thumbnails and library textures via `downgrade_files`).
4. Zip rewritten in FH2-native layout, copied to `Mount\media\cars\`, registered in `zipmanifest.xml`.
5. New files registered in `<game>\FH3Port\hash.manifest` (extended copy, original untouched).
6. Database rows ported into a working copy of `gamedbRC.slt`, integrity-checked, swapped in.
7. Shared files: converted tyre models, thumbnails (`stripped\RCFH3.zip`), missing library textures (appended to
   `cars\_library\Textures.zip`), FH3-only suspension XMLs (`media\Physics\Suspension`).

Backups: every touched file is copied to `<game>\FH3Port_Backup\files\` on first touch; created files and ported
cars are logged in `FH3Port_Backup\journal.json`; `restore` reverts all of it.

Plan numbers: 501 FH3 car zips → **214 new, 253 replace, 34 skipped** (30 zips have no FH3 database row – the
Porsche pack/DLC and `Shared.zip`; 4 traffic cars whose ids belong to different FH2 cars: FH3 2252–2254, 2408 vs
FH2's `*_H2_*` specials and `FOR_SVTRaptorCheetos_11`; renumbering is impossible because carbins embed part ids).

## Requirement: launch only with fh2sql.dll injected

New files (car zips, tyre zips, RCFH3.zip, suspension XMLs) are only visible through the extended hash.manifest that
`fh2sql.dll` hands to the game. Launching without the DLL while new zips are registered crashes at `game+0xfd1927`.
Mod Studio injects automatically; `start.bat` does too.

---

## Findings

### 1. The downloaded converter (ForzaToolsCli)
- .NET 9 single-file bundle; its own code is `stubcheck.dll` (extract with `research\fh3port\bundle_extract.py`,
  dump types/strings with `research\fh3port\mddump`).
- **Real:** `Fix.BundleDoc` (bundle parse/write), `Fix.MaterialConverter`, `Fix.ShaderRemap`, `Fix.ParamIO`
  (MTPR v3→v2 for top-level `.materialbin` only), swatchbin container downgrade, `manifest-line/-check`, `audit`.
- **Stubs:** `ForzaTools.Bundles.Bundle.Load/SerializeConverted` (2-byte bodies), `CarbinConversionService.ConvertCarbin`
  (7 bytes), `ModelbinConversionService` (2 bytes). `convert-carbin` prints OK and writes nothing; `convert-modelbin`
  writes 0 bytes; `analyze` returns nothing.
- Hidden verbs: `dump-mtpr`, `clear-mtpr` (look for MTPR blobs in modelbins; do not see the nested ones).
- Textures need an external `ForzaTools.TexConv.exe` (author's swizzler, `M:\_FH2.E_\Tools\Swizzler\…`) – not shipped.
- `fix-materials` needs `--fh3-lib "C:\Games\Forza Horizon 3\media\cars\_library"` (not `media\_library`).
- `manifest-check` guesses the path as `media\cars\<zip>`; for other folders only dirstart/dirsize/direntries count.

### 2. Why new files crashed the game, and the fix
- Crash `game+0xfd1927` = `App::Initialize → sub_140FD1600` (zipmanifest loop) → `CMultiVolume::vf42` (slot 0x210)
  returned null → dereference.
- The game's file index for `game:\` is **`Mount\hash.manifest`** (loaded by `CFileVolume::vf1B`): 12-byte records
  `u64 hash, u32 value`. Hash = `sub_14126E0D0(path, lowercase, 5381)` over the lowercased Mount-relative path with
  backslashes: `h ^= c + (h>>2) + (h<<5)` (32-bit) twice (second pass seeded with the first result), result
  `h | j<<32`. Value differs per file (content/chunk id) – new files copy a sibling's value. Files *listed* there
  work even when missing on disk (e.g. FH2's own `media\_library\textures.zip`); unlisted files are invisible.
- **Azimuth verifies `Mount\hash.manifest`** ("Incomplete or changed: Mount\hash.manifest is not version 1.0.0.64's")
  – it is the only data file it checks; other edits (gamedb, zipmanifest, renderscenarios, Textures.zip) pass.
- Fix: original stays; `fh2sql.dll` hooks the game's import slots (memory only, exe on disk unchanged) and hands the
  game `<game>\FH3Port\hash.manifest` when it opens `g:\hash.manifest` / `.\hash.manifest`; files Azimuth refuses
  are opened from Mount directly (never needed so far – Azimuth serves any disk file).
  IAT RVAs: CreateFile2 0x1DD1148, CreateFileA 0x1DD11B0, CreateFileW 0x1DD10C8, FindFirstFileExA 0x1DD1120,
  GetFileAttributesExA 0x1DD0F28, GetFileAttributesExW 0x1DD0FD8. Slot counts as resolved when ≥ 0x10000000.
- Call log: put `fh2sql_fslog.enable` next to the injected DLL → `fh2sql_fs.log`.
- Azimuth's crash box "This installation is modified" is only a label (shown whenever fh2sql.dll is loaded). No
  Azimuth fork/version supports added files; the developer does not support modded setups.

### 3. FH2 zip and manifest format
- Entries: deflate, version 0x0A, time/date 0, **central extra field 0x1123 (len 4) = absolute offset of the entry's
  data**, no local extra. Some Forza zips have no local headers at all, so the field matters. `fh3port.py`
  writes/extends zips in this layout (`write_native_zip`, `append_native`).
- `zipmanifest.xml`: `<Zip version="1" path="game:\…" priority="80" dirstart dirsize direntries/>`; dirstart = central
  directory offset, dirsize = CD size + 22, dirstart+dirsize = file size. Path lowercased. A zip `X.zip` mounts as
  folder `X\`; `_pri_NN` zips overlay the same folder.

### 4. Database port
- Schemas: 288 FH2 / 281 FH3 tables, 234 common; of 54 car tables 9 differ only by extra FH3 columns (dropped).
  No collations/indexes/views – plain SQL writes are safe; page size 1024, legacy format.
- Per-car tables (`Ordinal`/`CarId`): CameraOverrides, CarExceptions, CarInvalidDefaultParts, CarListFilters,
  CarPartPositions, CarsDropParts, Combo_Colors(+_Exceptions), Data_Car_Buckets, FreeRevOverrides,
  List_AntiSwayPhysics, List_SpringDamperPhysics, all List_Upgrade* by Ordinal, StripeColors, TrafficCars.
  Content tables (events, career, profiles, rewards, rentals, bucket list…) excluded.
- Families: engine (Data_Engine + List_UpgradeEngine*), drivetrain, body (Data_CarBody + CarBodyId tables), motor;
  stock wheel (List_Wheels); torque curves `List_TorqueCurve` (owned, overwritten); part manufacturers and other
  referenced rows inserted only when missing. Engine ids never collide with a different engine between the games.
- Lookup ids mean the same in both games except: **tyre compounds** (FH3 21 vs FH2 10, remapped:
  `{1:1,2:1,3:2,4:3,5:2,6:3,7:4,8:6,9:5,10:6,11:6,12:7,13:8,14:9,15:9,16:9,17:9,18:7,19:8,20:9,21:9}`, rows above
  FH2 slot 5 dropped), FH3-only suspension types 20–34 (rows + XMLs copied), cylinders, material types, 26 makes.
- Strings: FH2 ids are 32-bit (`_&3444174200`), FH3 64-bit. FH3 `.str` = u32[6] header (count at [5]), entries
  (u32 low32-of-hash, u32 byte offset), UTF-16 pool. **FH2 displays literal text in DisplayName/ModelShort/MakeName**
  (confirmed in the Autoshow), so FH3 English strings are written directly.
- Price: FH3 BaseCost (58 cars have ≤1 → median FH2 price of the class). Autoshow = `IsPurchased=1`.
- Thumbnails: FH2 naming `Thumbnail_<id>_Big/_Small.swatchbin` in `stripped\RC*.zip`; FH3 thumbnails go to new
  `stripped\RCFH3.zip`, `Thumbnail` column → `game:\Media\Stripped\RCFH3\Thumbnail_<id>.png`.
- Tyre models (`TireModelName` → `cars\_library\scene\tires\tire_<name>.zip`): FH3-only models are converted; the
  converter points their bundled materials at `game:\media\cars\<tag>\…`, so models go to the tyre folder and the
  bundle to `media\cars\fh3tire_<name>.zip`.

### 5. Material parameters (the crash on selecting the car) – fixed
- Crash `game+0x10c9b47` = `sub_1410C9920`, the shader parameter reader (via MaterialResource/ShaderResource/model
  material instances). Accepted types 0–9, 11; anything else leaves the object null.
- MTPR blob: u8 count, params `u8 maj, u8 min, u32 hash, u8 type, payload`, then a 12-byte trailer.
  **The version is per parameter**: FH3 v3.x params have a **16-byte GUID after the type byte**, FH2 v2.0 don't.
  Payloads: Vector/Color/Swizzle/FunctionRange 16, Float/Bool/Int 4, Vector2 8, Texture2D str7 path + u32,
  Sampler 8, ColorGradient u32 n + 4n. (Readers: `VectorShaderParameter::vf01` etc.)
- The converter downgrades top-level `.materialbin` but **not the material instances nested in `.modelbin`**
  (`MatI` blob → nested bundle with `RPTM`). `mtpr.py` strips GUIDs there and rebuilds nested + outer bundles
  (4-byte aligned). Validated: all 3,493 FH2 library materials parse; strict check after rewrite.

### 6. Geometry – tyres fixed, body still missing
Derived from FH2's readers (`sub_1413F1D70` model loader, `sub_1413F13C0` mesh, `sub_1413F2140` buffers) and
validated against FH2's own `tire_c` (same model in both games):
- Blob versions: FH3 Mesh 1.8 / Modl 1.2 / Skel 1.0 vs FH2 1.7 / 1.1 / 0.0.
- POSITION: FH3 RGBA16 SNORM (dxgi 13, Forza code 49); `xyz = snorm*scale + offset` with **per-mesh** scale/offset
  = the 32 bytes Mesh 1.8 appends; **w = normal.x** → FH2 RGB32 float (6/3). Error ≤ 0.000008.
- NORMAL: FH3 RG16 SNORM (37/52) = normal.yz → FH2 RGBA16 float (10/9) = (x, y, z, 0). Mean error 0.0005.
- TANGENT: FH3 RGB10A2 UNORM (24/48) → xyz = normalize(v·2−1), w = +1 if a ≥ 2 else −1 → FH2 RGBA16 float (10/9).
- TEXCOORD (35/46) and COLOR (28/22) unchanged. VLay trailer u32 = bitmask (TEXi → bit i, TANj → bit 5+j,
  COLOR → bit 10), identical in both games.
- VLay: u16 nsem, names (u32 len + chars), u16 nel, elements 20 bytes (u16 sem, u16 idx, u32 slot, u32 dxgi,
  i32 offset, u32 instance), u32 Forza code per element, u32 mask.
- Buffer (VerB/IndB/MBuf) header 16 bytes: u32 count, u32 bytes, u16 stride, u16 elements, u32 dxgi of first element.
  MBuf has the same format in both games.
- Mesh (FH2 1.7, 185 bytes for the tyre): fields in reader order; key ones: `i320` start index, `i324` base vertex,
  `u328` index count, index buffer id, then bindings `count × (i32 bufferId, u32 slot, u32 stride, u32 byteOffset)`
  (ids = each VerB's `Id` metadata, −1 = shared position buffer), 5 vec4 at the end. Mesh 1.8 = same + 2 vec4.
- Skel 1.0 = FH2 layout + one trailing u32 (any bone count). Modl 1.2 = FH2 + trailing u16.
- Result in game before the carbin fix: tyres correct, body invisible except one light (the CHMSL bulbs = the first
  model entry of the carbin – see 6b); driver visible.

### 6b. Carbin – the invisible body (fixed)
- Reader: `Car`'s scene ctor `sub_14117DC10` queues `game:\media\cars\<car>\<car>.carbin`; state machine
  `sub_1411A1910` case 2 wraps it in an `IOSys::CMemoryStream` and calls `CarScene::Scene::vf00` (0x1411AECB0).
  Stream slots: +472 u16, +464/+432/+416 u32, +392 f32, +480/+400/+448 u8, +376 string (u32 len + bytes), +280 GUID 16,
  +288 2×vec4, +352 vec4, +360 mat4.
- Layout (full detail in `carbin.py`'s docstring): Scene v5 → parts (u8 type: 43 wheel, 4 brake, else plain) → each
  Part v2 holds `CarRenderModel11` entries (reader 0x1411ADEE0) → upgradable parts v3 with upgrades v3 and more
  model entries; AOMapInfo v3 per model.
- **Only difference FH3↔FH2: model entries are version 0x10 in FH3; FH2 reads up to 0x0F.** v0x10 appends
  `u32 n + n × GUID16` at the end of each entry. FH2 does not know the field, so after the first entry every read is
  shifted → only the first model (`taillightCHMSLBulbs_a`, a light on the roof) rendered.
- Fix: version → 0x0F, drop the GUID list. `carbin.py check` parses all **354 FH2 and 500 FH3 carbins** to the exact
  byte with FH2's rules (FH3 with the v16 tail), and the downgraded NSX carbin parses as pure FH2.
- Checked and compatible as-is: `Lights.bin` (magic 0xDEADBEEF, v1, attachments/lights/LOD overrides – all 855 files
  parse; "9 vs 8" in the header is a light count). Not examined: `LightPresets.bin` ("LDFB", sizes differ),
  `physicsdefinition.bin` (car drives fine).

### 7. Textures (fixed, needs in-game confirmation)
- Swatchbin = bundle with `BCXT` blob + `HCXT` metadata. FH2's reader `sub_1410DBB90` (from `Texture11::vf0D`) has two
  paths: **blob version 2.0** = Xbox One tiled data + FH2's compact 35-byte header; **any other version** = "PC" path
  `sub_1410DC470` → `sub_1410A0360` (plain D3D11 `CreateTexture2D` with linear subresources).
- FH3 PC textures are blob **version 0.0** with exactly the header that PC path reads: relocatable struct (pointer
  chains: u32 at +0 = base chain, +4 = data chain; slots `u32 target, u32 next`, fixed up by `sub_1413E6FF0`), then at
  header+8: +16 width, +20 height, +24 depth, +28 u16 arraySize, +30 u8 mips, +31 u8 cube flag, +32 format,
  +40 sRGB, +48 ptr → (format id, per-slice mip tables of `u32 size, ptr data`). Format ids map through FH2's table
  (0 BC1, 1 BC2, 2 BC3, 3 BC4, 4 BC4s, 5 BC5, 6 BC5s, 7/8 BC6H, 9 BC7, 10 RGBA32F, 11 RGBA16, 12 RGBA16F, 13 RGBA8,
  14 B5G6R5, 15 B5G5R5A1, 19 R8, 20 A8). **So no re-tiling is needed** – FH2 loads FH3's linear data.
- What broke: FH3 sets byte +31 to **2 on UI textures** (thumbnails, gauge needles, gear digits; 2,484 in FH3), 1 on
  real cubemaps (arraySize 6). FH2 treats any non-zero as `D3D11_RESOURCE_MISC_TEXTURECUBE` → one-slice cubemap →
  creation fails → fallback loaders → white. Also BC thumbnails are 816×459 / 224×126 (not multiples of 4).
- Fix (`tex.py`): flag → 1 only for real cubemaps, else 0; round BC sizes up to a multiple of 4 when every mip keeps
  its block count (data is already block-padded). For the NSX: 3 thumbnails + 4 gauge textures changed; all its
  other textures are valid FH2 PC textures (verified by simulating FH2's reader).
- Some FH3 library textures (`Textures_pri_44.zip`) are already version 2.0 = FH2's own Xbox format.
- In-game result (2026-10-19): thumbnail correct; body visible but paint/interior **black**, carbon parts fine → 7b.

### 7b. Black surfaces (fixed, needs in-game confirmation)
Found with help of ForzaTechStudio's source (`ForzaTechStudio-Main`, see 10):
- **Vertex layouts:** FH3 adds a `COLOR0` channel (VLay mask bit 0x400) and `TEXCOORD4` to painted/interior parts.
  FH2's own models **never** have `COLOR0` and only have `TEXCOORD4` on glass together with `TANGENT4`. FTS's FH2
  target drops both. Each shaderbin carries `VDCL` metadata = the vertex-input masks of its compiled variants; none of
  FH2's 278 shaders declares the NSX's COLOR masks (0x47f/0x46f/0x44e/0x45e/0x47e). The parts that rendered (carbon,
  bays, lights) were exactly the layouts without COLOR. `geom.py` now drops `COLOR0` (and `TEXCOORD4` unless
  `TANGENT4` is present), rewrites buffer strides/element counts and rebuilds the VLay (names, codes, mask).
  Per-mesh check (mesh → MatI → materialbin → MATL shader → VDCL): FH2's Huracan 1163 exact / 8 superset / 0 none;
  NSX after the fix 547 exact / 847 superset / 0 none (before: 111 exact, 1283 only matching with COLOR dropped).
- **Paint list:** `ManufacturerColors.bin` = bundle with one `MNCL` blob: u8 groups, u8 entries, mask (FH2 blob 1.0:
  **u16**; FH3 1.1: **u32**), vec3 preview colour, 7-bit-length materialbin path. The converter only rewrote the bundle
  header, so FH2 got a 1.1 blob with u32 masks. `mncl.py` writes 1.0/u16. 39 FH3 cars paint a material slot ≥ 16
  (single bits 0x10000…0x1000000) that FH2 can't address – those entries keep the low 16 bits (logged).
- **Porter bug fixed:** engine/drivetrain families shared with a not-ported FH2 car (NSX engine-swap option =
  Huracan V10, engine 2292; drivetrain 2170) used to be deleted and rewritten from FH3 – this removed 3 supercharger
  upgrade rows of the FH2 Huracan. Shared family ids now keep FH2's rows; after the re-port 0 FH2 rows differ from the
  backup (only additions).

### 8b. Remapped materials – black lights and interior (fixed, needs in-game confirmation)
- In-game after 7b (2026-10-19): paint correct; headlights, taillights and interior flat black.
- Cause: for 58 of the NSX's 121 materials the FH3 shader does not exist in FH2. The converter then swaps in an FH2
  shader by a name-similarity score (lights: `lighting_ch1normlite_ch1mask → clc_metalch2normalch1mask`, score 0.36;
  interior: `int_ch2_simplenormalao_glossvar → int_m_ch2normglossalphaemissive`, …) but keeps FH3's parameters, so the
  FH2 shader runs without its own parameters/textures. List: `work\reports\<car>\fix_report.md`, "Remapped shaders".
- FH2's library uses other folders (`interiorengine\`, `basematerials\`, `lbk_*`/`gls_*` light materials) – 0 path
  matches, 22 file-name matches. `matmap.py` overwrites each remapped bundled materialbin (path kept, so no model
  changes) with: a hand-picked FH2 material (`MAP`, modelled on what FH2's Huracan uses: `lbk_custom_001`,
  `lbk_smoothchrome`, `blkplastic_*`, `blkleather_*`, `aluminum_*`…), else the same-named FH2 material, else it keeps
  the converter's remap when the score is ≥ 0.7 (5 cases; 2 symbol materials below that are logged).
  FH3 `radiosity\rad_*` (baked light-glow overlays, no FH2 equivalent) → `basematerials\gls_clear`.
- For other cars the log line "NO FH2 match" in the port output shows materials that still need a `MAP` entry.

### 8c. Light parameters (fixed, needs in-game confirmation)
- In-game after 8b: interior fine, headlight LEDs partly visible, light housings and taillights black / not lit.
- Shader parameters are 32-bit name hashes. FH3 and FH2 light shaders use **different parameter names** for the same
  settings: NSX taillight instance `Light Parameter`=69 (0x19416CFE), `LightColor` (0x448306EA), `CH1LightMap`
  (0x312DBAD1); FH2's Huracan taillight `LightFunctionCarLightParam`=69 (0x493073A0), `IlluminationColoColorParam`
  (0xC308C931), `LightMapTexture` (0x35C82561). FH2 ignores the FH3 names → no light function, glow or mask.
- Names come from ForzaTechStudio's `NameHashService.cs` – but only 389 of its 2,072 entries are CRC-32 of the name,
  so `lightparams.py` uses raw observed hashes, never computed ones.
- `lightparams.py` resolves the FH2 shader behind every MTPR (instance → materialbin → MATL → Shaders.zip) and renames
  a hash only if that shader lacks the FH3 hash and has the FH2 one (4-byte in-place change). NSX: 23 light ids,
  21 light masks, 15 colours. Unmapped FH3 light params still ignored: `Headlight_Color`/`DTRL_Color`/
  `Reverselight_Color` beyond the first colour, `TaillightSwitch`, `EmissiveSwitch`, brightness floats.

### 8d. Missing grilles / intercooler view (fixed, needs in-game confirmation)
- In-game after 8c: lights work, but front/rear intakes and side grilles empty and dark; the Autoshow thumbnail
  (rendered by FH3) shows honeycomb grilles there.
- No file is missing (all 123 carbin model paths exist). Mesh blob: `i16 material, i16 bone, u16 LODFlags, u8 minLOD,
  u8 maxLOD` (bit 0 = LOD S, bit 1 = LOD0, bits 2–6 = LOD1–5); carbin model entries have the same kind of u16 mask.
- FH2 uses `__SLOD` models (mask 0x1, meshes 0x1 / 255 / 255) only for hidden parts seen when panels open (trunk bay,
  hood liner, door jambs), always next to a regular sibling model. The NSX's honeycomb grilles exist **only** as
  `bumperFHoneycomb/bumperRHoneycomb/hoodHoneycomb/bodyHoneycomb_a__SLOD` → FH2 never draws them.
- `slod.py`: exterior `__SLOD` models without a regular sibling → meshes 0x1→0x3 (S+LOD0), minLOD 255→0, carbin
  entries 0x1→0x3 (`carbin.set_lod_masks`). Left alone: S-only pedals/seat belt (FH2's Huracan engine is S-only too).
- In-game after v1 (S+LOD0): grilles faintly visible in the Autoshow, not while driving; radiators/intercooler behind
  the grilles missing; taillight interior flickering.
- Mesh LOD byte order (from FH2's own data, 25 cars): `LODFlags, lastLOD, firstLOD` with 255 = S – e.g. S only
  `0x1/255/255`, S+LOD0 `0x3/0/255`, S..LOD1 `0x7/1/255`, LOD1..3 `0x1c/3/1`.
- v2: sibling-less `__SLOD` grilles → every LOD (`0x7f/5/255`, carbin `0x7f`); `__SLOD` models with a sibling (NSX
  `BumperF/trunkBay_a__SLOD` = front bay with the radiators, material `bumperframe_radiator`; engine, engine bay,
  liners, storage) → S..LOD1 (`0x7/1/255`, carbin `0x7`).
- Radiosity: FH3's `rad_*` glow overlays lie exactly on the light housings; as clear glass (`matmap`) they z-fight →
  `slod.py` sets their meshes' LODFlags to 0 (never drawn). NSX: 56 meshes.
- Minor leftover: some kept FH3 materials set `F0aVector4`/`F0bVector4` that their FH2 shader doesn't know
  (`research\fh3port\unknownparams.py`) – specular uses shader defaults there.

### 8e. Missing library textures and taillight z-fighting (fixed, needs in-game confirmation)
- In-game after 8d v2: grilles correct; the front intake still one flat black sheet, bumper parts without/wrong
  texture, taillight LED strip still flickering.
- Visual debugging without a 3D viewer: `research\fh3port\render.py` (numpy z-buffer, PNG writer, colour = model |
  material). The intake is a `bumperF_a` panel with `painted_metal_ch1` (black diffuse by design) whose look comes from
  instance textures `ptn_grillhexagon_*_nrml` / `_opac` and `grillbackground_innercooler_001_nrml`.
- `research\fh3port\texrefs.py`: the NSX's materials and instances referenced **121 shared-library textures FH2 does
  not have** (grille patterns, light masks, screws, stitches, grain normals…). The converter's MISSING report only
  covers carbin references (7), so the porter never copied them → black/flat surfaces. Now
  `fh3port.missing_library_textures()` scans every Texture2D parameter of the converted zip and adds what's missing to
  the copy list (FH3 library → `downgrade_files` → `cars\_library\Textures.zip`). After the re-port: 115 PC + 81 Xbox
  library refs resolve, 0 missing. (`game:\media\_library\textures\swatches\defaultshader*` refs are fine – FH2's own
  materials use the same paths from its packaged `media\_library\textures.zip`, which is not on disk.)
- Z-fighting: LED element `lights_ch1bump` (mesh 15, opaque) and glass overlay `gls_ch1_custom` (mesh 11,
  transparent) in `taillightL/R_a` are 0.027 mm apart (`research\fh3port\gap.py`, `overlap*.py`). Radiosity hiding
  didn't touch them. `zfight.py` moves such opaque meshes 1 mm along the glass normal; vertices shared only with the
  shadow-caster copy (material −1, bucket 0x9) move along, meshes sharing vertices with other visible meshes are left
  alone (NSX wheels). NSX: both taillights + one dash part moved.

### 8f. Reflectance names, FH3 reference shots (2026-10-20)
- User's FH3 reference: black hexagon grille with visible relief and reflections, chrome headlight internals,
  unlit taillights with an orange-red ring and a white/chrome inner reflector. FH2 showed these flat black.
- `research\fh3port\shnames.py`: FH2's `ch1/ch2diffnormglossalphaemissive` read reflectance as `F0a`/`F0b`, FH3's as
  `F0aVector4`/`F0bVector4` → every kept FH3 material on those shaders (intake panels, plastics, painted metal) lost
  its reflectance. `lightparams.py` now also renames by base name (type suffix ignored, suffix must fit the parameter
  type – a first version mapped `Gloss_floatVal` to `GlossTexture`, now rejected). NSX: F0a ×10, F0b ×7.
- FH3's normal shaders also carry `radColour1-3ColorParam_pg_radiosity` (radiosity tint); FH2 has no equivalent.
- Taillight render: the housing is almost entirely `lights_ch1bump` (FH3: near-black metal, F0 0.45, ridged normal
  map → reads as chrome in FH3's showroom) with radiosity layers interleaved (now hidden). Installed; awaiting user's
  comparison.

### 8g. Radiosity meshes are the lamp reflectors; stacked light layers (2026-10-20)
- In-game after 8f: grille relief visible; lamps still black; taillights flicker while driving.
- FH3 `radiosity
ad_*` materials (shader `rad_ch2_diffnorm`: metal F0 0.55 / non-metal diffuse 0.007, plus per-lamp
  tint colours) are the **reflector and housing surfaces themselves**, not overlays – hiding them (8d) left only the
  zeroblack backing visible. Now drawn again with FH2 materials (`matmap.MAP`): metal → `basematerials/chrome_polished`,
  non-metal → `basematerials/blkplastic_sgl`, glass → `gls_clear`; `slod.HIDE_RADIOSITY = False`.
- FH2's own lamps work differently: Huracan taillight housing = `lbk_plasticch3_001` (`ch3_nonmetallightbuckets`) with a
  per-car radiosity light map and red `IlluminationColorColorParam`; unlit it is near-black too.
- Driving flicker: FH3 stacks opaque light layers (taillight LOD0 meshes 12/13, **LOD1 meshes 20/21** = driving view,
  closest 0.003–0.02 mm) that FH3 blends. `zfight.py` second pass moves the smaller of two overlapping opaque meshes
  1 mm along its face normal (NSX: ~60 meshes across lamps, mirrors, dash, door handles, liners; wheels skipped –
  shared vertices). `research\fh3port\zpairs*.py` lists coplanar pairs per LOD.
- Third pass (2026-10-25, Alumi Craft side strip): parts that overlap only *locally* (a strip of a big mesh lying on
  another; Alumi Craft mesh 24 = 95 of 3,936 triangles, average normal ~0 so whole-mesh moves don't work). Triangles
  of the smaller mesh within 0.5 mm of the other **and** facing the same way (cos > 0.9) get their vertices moved
  1 mm out along their own vertex normals; at least 8 such triangles, vertices shared with other meshes stay.

### 8h. Wrong buffer decoding + shader-variant matching (2026-10-20)
- In-game after 8g: grilles correct; lamp housings/covers and the parts behind the grilles still black/wrong; flicker
  while driving.
- **geom.py bug:** each FH3 vertex buffer was decoded with the first layout of equal element count/stride. Models have
  several such layouts with different channels → 103 NSX meshes had buffers decoded/re-encoded with the wrong layout
  (e.g. `bumperF_a` buffers 2/3: 36-byte stride, layouts 32/40 bytes) → wrong UVs/tangents. Now the layout comes from
  the meshes (layout index + binding slot). `research\fh3port\strict.py`: installed NSX 103 mismatches, new 0,
  FH2 Huracan 0. (`consist.py` used the same guess and missed it.)
- **Exact variants:** FH2's own cars match a compiled VDCL variant exactly in 99.3 % of meshes (`exactness.py`, 8 cars:
  9,303 exact, 67 superset, 0 bare). The NSX had 847 supersets and 258 meshes that only fit the bare 0x0 variant.
  `vlayfix.py` picks per mesh the variant needing the fewest added, then dropped channels; drops extra TEXCOORD/
  TANGENT, adds missing ones copied from the nearest same-kind channel; edits in place when all users agree, else adds
  new VLay/VerB blobs (`bundle.py`). NSX: 254 changes → 1,394 of 1,394 meshes exact.

### 8i. Crash game+0xfd841f after adding blobs (fixed 2026-10-21)
- The 8h build crashed ~30 s after start: `sub_140FD8400` (smart-pointer release of 0xfffffff3) called from the buffer
  reader `sub_1413F2140` ← model loader `sub_1413F1D70` (`research\fh3port\mdstack.py` reads the Azimuth minidump
  stack; the dump has no module list, base 0x140000000).
- `Modl` starts with `u16 meshes, u16 buffers (VerB+IndB+MBuf), u16 layouts (VLay), u16 materials (MatI)` (+ flags);
  the loader allocates exactly that many 96-byte buffer slots and checks the count. New VerB blobs without updating it
  wrote past the array. All 91 Huracan models follow the rule (`research\fh3port\modlcounts.py`).
- Layouts are filed **by position** (`sub_1413E9B30` walks the VLay blobs in order into an 80-byte array) and meshes
  address them by position (FH2's own last, empty layout has Id −1 at position 6 and is used as 6). Buffers are looked
  up by Id. `vlayfix` now appends layouts with Id = position, gives new buffers fresh Ids and rewrites the `Modl`
  counts; `geom.py` also maps mesh layout indexes by position.

### 8j. Black lamp units – investigation (2026-10-21)
- Lens meshes are fine: glass materials/parameters compatible (`OpacityColorMultiply` 0.25, red `GlassColor`), layouts
  exact, bucket order 0 is normal in FH2 (2,324 transparent meshes). Glass over a black interior simply shows black.
- **Light-function ids are identical in FH2 and FH3** (`research\fh3port\lightfuncs.py` → `lightfunctions.json`; table of
  `Offset_<Name>` + id in both exes): 0 Brake, 1 Reverse, 13 Headlight, 15 DayTimeRL, 17 HighBeam, 20/21 turn,
  32 Taillight, 69 TailBrakeLight, **70 Null**; FH3 adds 71 HighHeadLight, 72 MarkerLight. NSX ids port 1:1; its
  70-layers are deliberately unlit base layers. The orange ring in the FH3 showroom shot = tail lights on (32/69).
  FH2 lamps are mostly dual-function (`LightFunction` + `LightFunctionB` 70 + `DualBrightSwitch`).
- **AO maps:** FH2 gives every main lamp model a carbin AO map (15 cars: only bulbs, lenses, interior LOD lack one);
  FH3 does too (82/82 sampled lamps) – **but the FH3 NSX has empty AO entries for headlightL/R, taillightL/R/C,
  taillightCHMSL, doorHandleRF** (it lights its lamps via `textures/lp/*_radiosity` + `rad_*` materials instead).
  FH2 (`CarRenderModel11::off10_vf07` 0x1411BF8A0) loads the AO texture only when the path is non-empty and otherwise
  leaves the slot (+336/+376) null; the draw-time binding/fallback is not located yet. A null SRV samples as 0 →
  the whole lamp interior black regardless of material. Exactly the black parts lack AO.
- FH2 does the "lit lamp" look with per-car radiosity textures too (Huracan `Textures/LP/*Radiosity_Diffuse{Front,Rear}
  Reflector*`, `*GlassCover*`) used as `LightMapTexture` on `lbk_plasticch3_001` (`ch3_nonmetallightbuckets`) with
  `LightFunction` 69/70 and a red `IlluminationColorColorParam`. The NSX has the FH3 equivalents
  (`Textures/lp/front_reflector_radiosity`, `rear_reflector_radiosity`, `front_glass_radiosity`).

**Step 1 (2026-10-21): no visible change in game** – kept (harmless; FH2 lamps always have an AO map), real cause in 8k. `aofix.py` writes
`game:\media\cars\<car>\textures\ao\fh2port_white_ao.swatchbin` into the empty AO entries of headlightL/R,
taillightL/R/C, taillightCHMSL, doorHandleRF (`carbin.set_ao_paths`; strings are length-prefixed, no absolute offsets).
The texture is the car's smallest BC4 AO swatchbin with every block set to white and a fresh GUID.

**Plan (black lamp units):**
1. Verify AO (cheap A/B): give every model with an empty AO entry a neutral white AO swatchbin (new 4×4 BC4 texture
   in the car zip, path written into its carbin `AOMapInfo`; carbin parser already has the offsets). In game: lamp
   interiors should turn from black to shaded chrome/plastic. If not → IDA: find the draw-time AO binding and its null
   fallback (start from the AO resource handle at CarRenderModel+336).
2. If 1 works, generalise in the porter: `aofix.py` fills every empty AO entry of a drawn model (all cars).
3. Lamp look like FH2/FH3 when lit: map `rad_ch2_metal/nonmetal` to an FH2 light-bucket housing (`lbk_plasticch3_001`
   style, `ch3_nonmetallightbuckets`) with `LightMapTexture` = the NSX `*_reflector_radiosity` texture, light functions
   from the FH3 instance (tail/brake), red/white `IlluminationColorColorParam`; `rad_smoothglass` (headlight cover) →
   FH2 illuminating glass (`gls_customlitnormopach1_002` style) with `front_glass_radiosity`. Needs: how FH3 binds the
   `textures/lp` maps to the rad meshes (instance params vs. carbin) – check with `instparams.py`/IDA on FH3.
4. Optional: daylight look. FH3's showroom shows tail lights on; FH2 turns them on only with headlights. Leave as is
   unless wanted (would mean forcing `TaillightAmount` via fh2sql).

### 8k. Real cause of the black lamps: depth-pass vertex layouts (fixed 2026-10-21)
- White AO (8j step 1) changed nothing. Comparing the lamp units with FH2's: materials are genuine FH2 library ones,
  glass parameters match FH2 cars (`research\fh3port\lampglass.py`), geometry faces outwards
  (`render.py` with `CULL=pos`), carbin model entries are equivalent (`carbinfields.py`; v11 fields are only
  Receives{Impact,Splatter,Damage,Dirt,Oil,Rubber}). What differed: the vertex layouts.
- A shaderbin's VDCL holds **one vertex-input mask per render pass** plus a second entry with the full mask (= their
  union), e.g. `m_ch1normglossalphaemissive`: passes `0x2f 0x0 0xf 0x6f 0x1 0x6f 0x6f 0xf`, full `0x6f`
  (`vdclgroups.py`). The small masks are depth/shadow passes (`0x0` position only, `0x1` alpha UV only).
- FH2's own cars always supply the full mask: 10 cars, 11,597 of 11,597 drawn meshes (`superset.py`); 15 cars:
  12,773 of 12,774 exterior meshes carry TEXCOORD2.
- vlayfix (8h) matched *any one* mask ("fewest added channels") and so gave 221 NSX meshes a depth-pass layout,
  dropping TEXCOORD2/3 and tangents (`notex2.py` against a pre-vlayfix build from `prevlay.py`): nearly all lamp
  housing meshes became `0x1`, the lamp glass `0x4e` instead of `0x4f`. Before vlayfix the same meshes were `0x25`
  etc. – also short of the full mask. In total **693 NSX meshes lacked inputs** (lamps, lamp glass, mirrors, parts of
  bumpers/body/door handles/wipers). Such a mesh fits the depth pass but not the colour passes → black / missing.
- Fix: `vlayfix` now targets the union of the shader's VDCL masks; layouts already containing it are left alone,
  others are rebuilt for exactly that mask (missing channels copied from the nearest one of the same kind).
  NSX after the fix: 1,394 of 1,394 drawn meshes supply the full mask, 0 without TEXCOORD2; strict 0, Modl counts 0,
  verify 0, carbin 0. Installed 2026-10-21, → Azimuth stopped at startup.
- Crash: `D3D12 graphics pipeline vs=1011 ps=0 ... HRESULT=0x80070057`, inputs `... TANGENT0:35 TANGENT0:35`
  (`amzimuth\data\logs\azimuth.log`) – a depth-pass pipeline with a duplicate TANGENT0. Cause: layouts that already
  *contained* the full mask were left alone, giving (shader, mask) pairs FH2 never uses (`research\fh3port\combos.py`,
  40 cars: zeroblack 0x4e vs FH2 0x4, rotor 0x6f vs 0x2d, undercarriage 0x6f vs 0x67, INT_* 0x4e vs 0x46...).
  Now **every** layout is rebuilt to exactly the full mask. Left over: 3 shaders no sampled FH2 car uses
  (car_cf_embossed_interior, clc_diffusemetallerpch1masknorm, int_m_ch2normglossalphaemissive) – exact full mask.
  Reinstalled 2026-10-21 (strict/Modl/verify/carbin 0), → still crashed:
- Still crashed (same error, vs=1008). Findings: the 7,184-byte VS is `ambientvehicle_shadow…Skinning_Instanced`
  (`tracks\anthem\bin.zip`; inputs POSITION, TEXCOORD0 + instance data) – the shadow of ambient/traffic cars. All
  91,521 VLay blobs in the install are well-formed (`research\fh3port\badvlay.py`), and FH2 hands the VLay
  elements to the input layout unchanged (`sub_1413F2CD0`: the 32-byte entries are D3D11_INPUT_ELEMENT_DESCs), so the
  bad descriptor is built at runtime. What differed from FH2 and from the old build that ran: layouts/buffers per
  model – FH2 max 10 VLay / 25 buffers, old build 15 / 28 (`oldvlay.py`), this build 17 / 30 (appended duplicates +
  stale blobs).
- Fix (`vlayfix`): new layouts identical to an existing one are merged, and VerB/VLay blobs no mesh references any
  more are dropped (`drop_unused`, layout positions remapped). NSX now: max 11 layouts (dashStructure, as in FH3) and
  22 buffers, every mesh still supplies its full mask; strict/Modl/verify/carbin 0. Installed 2026-10-21. The
  per-model limit is inferred, not confirmed in IDA – if Azimuth still refuses, find the ambient-vehicle
  input-layout builder next.

### 8l. VLay data audit; invented UV channels had identity transforms (fixed 2026-10-23)
- The 8k build runs (no crash) but still looks wrong. Audit of every VLay-related property, NSX vs FH2
  (`research\fh3port\`): layouts byte-identical to FH2's for the same mask; normals unit length and facing like the
  triangles (`nrmcheck.py`, 100 % on both); NORMAL.w = 0 in FH2 too; tangents unit, orthogonal, TANGENT0 follows
  TEXCOORD0 and TANGENT1 follows TEXCOORD1 with matching handedness (`tancheck.py`: NSX 98–99 %, FH2 87–100 %);
  per-mesh UV transforms (Mesh >= 1.5, last 80 bytes = 5 × offset.x, scale.x, offset.y, scale.y) in FH2's convention
  (`vstats.py`). ForzaTechStudio's VLay patch uses the same rule as vlayfix (union of VDCL masks, add missing
  elements); its normal conversion (SNORM16x2 -> half4 as x,y,0,1) is wrong for FH3 data, ours is validated.
- Found: channels FH3 never had keep an identity transform (0,1,0,1) in the mesh (absent T0 ×721, T1 ×261, T3 ×286).
  vlayfix filled them with a copy of the nearest channel's raw UNORM data but not its transform, so e.g. `frame`
  (81 meshes, real UVs on TEXCOORD1 spanning 11.6–21.7) got a TEXCOORD0 spanning 0–1 -> its maps sampled a tiny,
  stretched patch. Affected (`synth.py`): frame (T0), lamp housings lights_ch1bump (T1,T3), rad_* (T0,T3), lamp and
  window glass (T0/T4), grille_012 (T0,T3), chrome, interior trim.
- Fix: `vlayfix.copy_uv_transforms` copies the source channel's transform into the invented slot (865 channels on the
  NSX, existing transforms untouched). strict/Modl/full-mask/verify/carbin 0. Installed 2026-10-23, awaiting test.

### 8m. Azimuth pipeline refusals: position-only layout must be last (fixed 2026-10-25)
- User test of 8l: **the car renders correctly**, but Azimuth still stops after a while (car meet with several cars):
  `D3D12 graphics pipeline ... HRESULT=0x80070057`. `amzimuth\data\logs\azimuth.log` lists the refused input
  layouts; all are NSX-shaped layouts whose tail is replaced by repeats of an earlier element: 0x6f layouts as
  `… TEXCOORD1 ×5` or `… TANGENT0:35 TANGENT0:35`, T1 T2 TAN1 as `TEXCOORD1 TEXCOORD2 TEXCOORD2`, T0 T2 TAN0 as
  `TEXCOORD0 TEXCOORD2 TEXCOORD2` (duplicate semantics -> D3D12 refuses). Depth passes (ps 0) and a forward pass.
- Shader sizes in the log are not unique (36 vertex shaders are 9,992 bytes), so the earlier "ambientvehicle_shadow"
  match is not reliable. The minidumps hold only ~2.7 MB of stacks (no heap) (`research\fh3port\mddesc.py`).
- FH2 invariant (40 cars, 3,423 models, no exception): every VLay's Id equals its position, except ONE position-only
  layout (1 element, mask 0) with Id -1, which is always the LAST layout. FH3's originals follow it too; vlayfix
  appended new layouts after it (NSX: -1 in the middle of 25 models, `taillightCHMSL` even first). The game evidently
  takes the last layout as the position-only one for its depth/shadow streams.
- Fix: `vlayfix.position_only_last` moves Id -1 layouts to the end, renumbers the rest Id = position, remaps mesh
  layout indexes. Mesh data and the layout content each mesh uses are byte-identical to the 8l build (1,972 meshes).
  NSX + converted tyres: 0 models break the order; strict/Modl/full-mask/verify/carbin 0. Installed 2026-10-25; user test: same crash -> 8n (the order is kept anyway, it matches FH2).

### 8n. The crash cause: stale blob size fields (fixed 2026-10-25)
- Traced in IDA (FH2 exe, functions renamed in the .i64): `Mesh_BindForDraw` (0x1413F4360) takes the layout object
  `model+184[mesh+340]` and hands its element vector unchanged to `InputLayout_RequestForVertexShader` ->
  `InputLayoutCache_FindOrCreate` -> `InputLayoutResource11_Create` -> `D3DDevice_CreateInputLayout` (device vtable
  +0x58). Nothing filters or pads elements; the game never parses ISGN. `Model_LoadFromBundle` (0x1413F1D70) also
  loads `ILay` (0x494C6179) blobs into `model+200` for instanced draws - car models have none.
- So the element vector itself was bad. `VertexLayout_ReadBlob` (0x1413F2CD0) reads each element as a 20-byte record
  into a reused buffer; when the blob's data ends early the read fails and the element keeps the previous record's
  values - exactly the repeated `TEXCOORD1 ×5` / `TEXCOORD2 TEXCOORD2` tails in azimuth.log.
- Cause: `bundle.serialize` wrote each blob's second size field (`usize`) as parsed. vlayfix edits VLay/VerB blobs in
  place, so grown blobs kept their old, smaller value. Installed NSX: 237 blobs with size != usize (49 VLay and 68
  VerB declared smaller than their data). FH2: 0 of 71,748 blobs (20 cars + Shaders + Materials); NSX before vlayfix:
  0 of 4,076. FH2 evidently sizes the blob data by that field.
- Fix: `bundle.serialize` always writes the real data length into both fields (FH2 round-trip still byte-identical,
  91/91 Huracan models). Rebuilt NSX: blob data identical to the 8m build, 0 size mismatches in the car, tyres,
  thumbnails and the library Textures.zip; strict/Modl/full-mask/verify/carbin 0. Installed 2026-10-25.

### 9. Engine sound (solved by borrowing FH2 engine sounds, 2026-10-25)
- FH3's FMOD banks are format 78 + Opus, FH2's format 46 + XMA; FH2's FMOD can't load them and no tool downgrades.
- IDA (renamed): `Audio_GetCarEngineBankIds` (0x140292840) runs
  `SELECT MediaName FROM Data_Engine DE, List_UpgradeEngine LU WHERE DE.EngineId = LU.EngineId AND Ordinal = %u
  UNION ... Data_Motor ...` and loads `media\audio\fmodanthem\durango\PG_<engine MediaName>.bank` for every engine
  of the car (stock and swaps); `Audio_BuildCarEventPath` (0x1410103A0) builds `/Master/PG_Cars/<name>/<name>_…`.
  **The sound belongs to the engine (`Data_Engine.MediaName`), not the car** - that is how engine swaps change the
  sound. Every lookup goes EngineID -> name, so engines may share a name.
- Ported NSX: stock engine 2482 was `ACU_NSX_16` (no bank -> silent); its swap option, the Huracan V10 (2292), always
  had sound.
- Porter: `Porter.fix_engine_audio` gives every ported engine without an FH2 bank the MediaName of an FH2 engine
  that has one: `AUDIO_DONOR` (NSX -> `NIS_GTR_12`, twin-turbo V6; Centenario -> `LAM_LP7004_12`, the same 6.5 V12),
  otherwise the closest by cylinders, layout, aspiration, power and make (`audio_donor`; it picks the same two
  donors). No DLL hook needed. Also applies `media\audio\cars\<name>.xml` (physics modulation) of the donor.

### 10. ForzaTechStudio source (`ForzaTechStudio-Main`)
Full C# source of the original tool (the CLI in `Forza Horizon 2 Convertor` is a patched build with these stubbed).
Useful parts: `Services\ModelbinConversionService.cs` (per-game VLay tables, FH2 target formats, VDCL-driven
"advanced VLay patch"), `Services\SwatchbinConversionService.cs` + `Native\xg.dll` (PC↔Xbox tiling – not needed,
FH2 reads PC textures), `ForzaTools.Bundles\Blobs\*` (blob layouts: Mesh, MNCL, MatL, VDCL…),
`Services\CarbinConversionService.cs` (game version table: FH2 = carbin 5 / model 15), `LightPresetsBinParser.cs`
(V1 for FH2–FH4, so `LightPresets.bin` is left as is).

### 8. Useful addresses (FH2 exe, base 0x140000000)
`sub_140FD1600` zipmanifest loader · `IOSys::CMultiVolume::vf42` open (0x1411F49B0) · `CFileVolume::vf1B`
hash.manifest load · `sub_14126E0D0` path hash · `sub_1410C9920` shader param reader · `sub_1413F1D70` model loader ·
`sub_1413F13C0` mesh reader · `sub_1413F2140` buffer reader · `CarScene::Scene::vf00` 0x1411AECB0 carbin reader ·
`CarRenderModel11::vf00` 0x1411ADEE0 carbin model entry · `sub_1411ADD20` Lights.bin · `sub_1410DBB90` texture
reader (2.0 vs PC path) · `sub_1410DC470`/`sub_1410A0360` PC texture creation · `sub_1413E6FF0` pointer fix-up · `sub_140F697B0` wheel offsets (CarTrackOffsets, dead
data) · `sub_141047FA0` body-part upgrade record check · `sub_1410F82F0` version compare helper.

---

## Open problems and next steps

1. **In-game test of the re-ported NSX** (material substitution for lights/interior). If parts stay dark: check
   which material they use (`research\fh3port\bypart.py`, `meshcheck.py`) and extend `matmap.MAP`.
2. Then `fh3port.py port all` (467 cars).
3. Engine sound: alias hook (finding 9) – needs the IDA MCP server running.
4. Note: the converter's release readme itself lists `convert-car` geometry/carbin/TexConv as stubs in both the
   Windows and Linux builds; the stages above replace them.

## research\ folder
- `fh3port\` – analysis for this port: schema/lookup comparison, string formats, hash.manifest, zip/manifest,
  material/geometry/texture format diffs, validators (`geomtest.py`, `tangent2.py`, `vlay_inv.py`, `meshfields.py`),
  crash-dump readers (`dump3.py`), converter extraction (`bundle_extract.py`, `mddump\`).
- `ida\` – IDA scripts (run via `ida.py py <file>` against the ida-pro-mcp server on :13337).
- `modstudio\` – Mod Studio upgrade/spacer research and UI automation tests.
- `misc\` – earlier database/render-distance research.
Paths inside the scripts point at the session scratchpad; adjust before reuse.

## 10. Paints, stickers, plates, database checks, Mod Studio tab (2026-10-27)

- **Manufacturer colours black** (Aston greens, R8 greens): `ManufacturerColors.bin` points every swatch at a paint
  material; FH3-only paints (`allorogreen`, `greenam`, `cumbriangreen`, `mysticgreenss`, ...) are missing from FH2's
  library, so the paint falls back to black. `mncl.py` now copies each missing paint from FH3's library into the car zip
  (`materials/carcolors/<name>`, converted burG 1.1 -> 1.0, MTPR v3 -> v2, strict-checked) and points the swatch there -
  the way FH2's own Zagato ships `quantumsilver2`. Same-name paints in both libraries were compared: identical apart
  from an extra FH3 texture parameter, so FH2's versions stay.
- **Black sticker blocks + flicker** (Audi S1 #2, Alumi Craft): FH2 alpha-tests `ATST` materials only in the depth
  pre-pass (`carpaint_standard...ShadowDepth...pso` has `discard_nz`, the colour pass has none and draws where the
  depth matches). FH3 keeps sticker overlays 0.2-0.5 mm above the paint, so even their transparent (black) texels
  match the paint's depth. FH2's own overlays sit 0.5-2 mm out. `zfight.py` decal pass: meshes with render pass
  0x38 (neither opaque 0x01 nor transparent 0x04) within 0.5 mm of an opaque surface of the same model or a sibling
  model of the part (`hoodLivery_a` over `hood_a`) move 1 mm out along their vertex normals. S1: 31-73 % of sticker
  triangles within 0.5 mm before, 0-1 % after.
- **Licence plates**: FH2 has no plate text (a row of zeros). `plates.py` hides `plateUS_*`, `plateEU_*`,
  `fplateEU_*`, `plateManu_*` (LODFlags 0, files kept for the carbin); plate lights and brackets stay.
  `fh3port.py port ... --keep-plates` keeps them.
- **Database validation** (`dbcheck.py`): every row is checked before it is inserted (dropped FH3-only columns with
  data, types, enumeration values FH2 never uses) and read back afterwards (exact values except the porter's known
  rewrites; references FH3 resolves must resolve in FH2; make/name/price/bucket/engine-sound rules). Errors fail the car
  (savepoint rollback), reports in `work/dbcheck/<car>.txt`. A failed re-port keeps the previously installed version.
- **FH2 Mod Studio "Port FH3 cars" tab** (sidebar, Ctrl+5): search + status filter + car dropdown, list of chosen cars,
  "Import licence plate" checkbox, Convert & install (live log, per-car result), Undo this conversion, Re-check
  installed cars. Backend: `batch_port.py cars-json | port-cars [--keep-plates] CAR... | check CAR... | undo <snapshot>`.

## 11. Paint groups, interior colours, car names in menus (2026-10-27)

- **Paint groups** (Centenario painted only on its yellow accents, carbon body black): every carbin model entry
  (v3+) carries a list (material instance name -> u32 paint-group mask); this is what the old notes called
  "(str, f32)". FH2: `Presentation11::CarPresentation::vf53` (SetPaintGroupMaterial) -> sub_1411B4A60 ->
  `CarRenderModel11::off10_vf27` applies a colour to every instance whose mask overlaps; table read by sub_1411B0270.
  Bits mean the same in both games (59 shared cars compared): 0 body, 1 livery, 2 hood, 3 mirrors, 4 wing,
  7 windows, 8-11 secondary paint, 12-15 second colour of body/hood/mirrors/wing (FH2 paints those with the two-tone
  colour, black by default). The Centenario is the only FH3-only car without bit-0 groups: its carbon body sits in
  0x1000-0x8000. `carbin.remap_paint_groups` moves 0x1000/0x2000/0x4000/0x8000 -> 0x1/0x4/0x8/0x10 for such cars.
- **Interior colours** (white/red seats instead of black/yellow): FH3 sets `ColorColorParam` (and `Gloss_floatVal`,
  `F0Vector4`); FH2's shaders call these `DiffuseColorGroupColorParam` or `DiffuseColorA/B`, `GlossA/B`, `F0a/F0b`.
  `paramexpand.py` writes the value into the FH2 parameter(s) the resolved shader knows, and restores colours the
  converter dropped when it swapped an FH3-only shader (suede_custom: fabric_colorlookup -> int_ch2normglossch1maskdiffuse).
- **Names in pause/race menus**: the menus resolve string ids; the porter wrote plain text. FH2 string ids are
  (table hash << 16) | key (Data_Car 0xCD49, List_CarMake 0x3323). `.str` = LSB2: header, section 0 = u32 size, u32
  count, (count+1) x (u16 key, u32 UTF-16 offset), sorted, 0xFFFF sentinel, UTF-16 pool (reader sub_141246F30; only
  section 0 is read). `strtables.py` rebuilds tables byte-identically when unchanged (36 of 36 tested) and adds the
  ported cars' DisplayName/ModelShort and new makes' DisplayName/Profile in all 18 languages with FH3's translation of
  the same language. Keys are kept per FH3 id in the journal. `fh3port.py names` (Mod Studio: "Write car names") does it
  for installed cars; every conversion does it automatically.
- **Mod Studio Port tab**: FH2 / FH3 install locations and the converter path can be set (written to fh3port.ini).
- **Race-livery base paint black** (GT-R #1 NISMO, Focus RS RX; decals fine, other colours fine): the stock
  manufacturer colour is a car-specific `*_baselivery` paint on `carpaint_standard_glossmask`, a shader only FH3 has, so
  FH2 can't build it. `mncl.remap_paint_shader` moves colour-list paints to `carpaint_standard` (same paint without
  the gloss mask) and switches `CH1DiffuseTextureSwitchBool` on so the livery texture is drawn. FH3-only cars with a
  paint on another FH3-only shader: Corvette Z06 Horizon Edition (`cf_outlinech1`, not mapped yet).

## 12. Several FH3 media folders, picked zips, DLC cars, collision (2026-10-27)

- **Media folders** (`fh3lib.py`): `fh3port.ini [paths] fh3` (the install, uses `<fh3>\media`) plus optional
  `fh3_extra` (more media folders, `;`-separated, searched first). Both are set in FH2 Mod Studio's Port tab
  (FH3 install location / FH3 update / DLC media, Browse + Clear); nothing is hardcoded. Car zips, the database
  (`stripped\gamedbRC.slt`), string tables, thumbnails (`stripped\RC*.zip`), physics files and tyre models come from the
  first folder that has them. Library zips are layered per folder (`Materials_pri_45 > _pri_44 > Materials.zip`, same
  for Textures, names case-insensitive) and across folders; the converter gets one merged `work\fh3lib\Materials.zip`.
- **Picked zips**: `port` / `port-cars` accept a path to a car zip anywhere on disk (Mod Studio: "Add zip file…"). The
  zip's name must be the FH3 MediaName; its database row comes from the FH3 database.
- **Car list** (`fh3only.json`) is rebuilt automatically when the media folders or the FH3 database change.
- **Paints kept for the converter** (`prepatch.py`): every car-local material the car's ManufacturerColors.bin names
  (not only `materials/carcolors|carliveries/`: Fortuna `materials/livery/`, 944 `materials/basematerials/` …), with their
  textures from FH3's media and car libraries. Paints on `carpaint_standard_glossmask` (Hoonigan / race base liveries) or
  with textures FH3 ships nowhere (Regalia carbon flake) are held back from the converter and added afterwards
  (`mncl.convert_material`; missing textures -> closest-named library texture, `mncl.retarget_textures`). Library paints
  in no FH2/FH3 library (por_hoonigan_91 whitepearlmatte) use FH2's closest-named paint.
- **Collision** (`physdef.py`, crashes 8 and 9 in CRASHES.md): FH2's 4 KB physics arena and the
  ChildRenderModelIndices table.
- Work scripts: `work\dlcdry.py` (dry-convert the extra folders' cars), `work\drycheck.py` (model, collision and paint
  checks on dry zips), `work\paintscan.py` (installed ported cars with unresolved paints).

## 13. Thumbnails, manufacturer logos, FH3 engine audio research (2026-10-27)

- **Thumbnails** (`fh3port.fh3_thumbnails`): FH3's Thumbnail path often names no RC zip
  (`UI\Textures\Thumbnails\Thumbnail_<id>.png`: DB11, Miata, King Cobra …) or another id (Hoonicorn 1184 ->
  `RC21\Thumbnail_2734`). Every media folder's `stripped\RC*.zip` is indexed; the path's id first, then the car's id.
  541 of 545 FH3 cars have one (none in FH3 for mer_slr_05, chr_gtx_71, for_falconute_14, sub_75_wrxstivt15r_16).
- **dlc_synth** only for cars FH3's database lacks: the update database has real rows for all 29 of its cars, which
  had been ported with donor data (stats, engine, thumbnail).
- **Logos** (`logos.py`): makes whose IconPath/IconPathLarge FH2 can't load (FH2's own Holden/Chrysler rows point at
  RC0 files that don't exist; makes added from FH3 keep FH3 paths) get FH3's logo in RCFH3.zip; every port run.
- **Engine audio** (`research\fh3port\fmodbank.py`): FH2 banks are FMOD bank format 46 with XMA samples, FH3's format 78
  with FADPCM (plus GS_ granular banks FH2 has no use for). FH2's FMOD can't load 78. Same Forza parameters in both
  (EngineRPM, Backfire, Blowoff, GearRatio ...), but the Huracan's FH3 bank shares no waveform GUIDs with FH2's, has
  94 vs 91 samples, stereo and 10 s recordings: re-authored, so FH3 samples can't be mapped onto FH2's slots by
  identity. A transplant (FH2 bank structure + FH3 recordings decoded from FADPCM, stored as PCM16) needs FH3's
  instrument -> RPM layout from its bank metadata (WAIS/MUIS/parameter sheets, format 78) or an RPM estimate per
  sample from its firing frequency.

## 14. New upgrade entries, drift/drag parts, tuning ranges (2026-10-28)

- **How the upgrade shop lists parts** (IDA, shop SQL): a part row shows only if `Upgrades` has a row for its
  (`UpgradeTypes.id`, `Level`) or a level `-1` wildcard for the type: `Upgrades.Level = PartTable.Level OR Upgrades.Level = -1`.
  Stock: springs (type 13) levels 0-4 Stock/Street/Sport/Race/Rally, tyres (21) 0-5 (4 = Drag, 5 = Rally), brakes (12)
  0-3, anti-roll bars 0-3. **To add an entry** (more suspensions, tyres, ...): rows at one fixed new level for every car +
  one `Upgrades` row (id, TypeId, IsException 0, Name, Level, Description, IconPath, ImagePath) whose Name/Description are
  `Upgrades.str` string ids (hash `0x7091`, key free in all languages; `fh3port.py upgrade-strings` writes the texts).
- **FH2 Mod Studio drift & drag parts** (`research\modstudio\driftdrag_gen.py` -> `DriftDragPack.Data.cs`): drag tyres tyre
  level 4 (FH3 `19_Drag` as compound 21), drift tyres tyre level 6 (FH3 `18_Drift`, low grip, compound 22, Upgrades 275,
  strings `0xD002/0xD003`; not on the 5 off-road cars whose factory tyre is on level 6), drift suspension spring level 5
  (Upgrades 274, strings `0xD000/0xD001`), default alignment front camber -5, rear -1, rear toe -0.05.
- **Drift steering**: `fh2sql.dll` (`dll\fh2sql.cpp`) sets lock/speed while the drift suspension is installed; `[drift]` in
  `fh2sql.ini`, live via pipe request `#drift <lock> <speed>` (next car load).
- **Tuning ranges**: `PhysicsSettings.ini` `[CarTuning]` keys are bound to floats of the physics settings object
  (pointer `0x14365D6E8`, `TuneFinalDriveRatioMin` +608 ... `TuneGasTankFillMax` +728, `sub_14104E390`). FH2 Mod Studio
  "Drift setup & tuning ranges…" edits the file (original kept as `.orig`) and, in game, the live floats.

## 15. Material conversion, texture swaps, make-logo shape (2026-10-28)

- **White / grey / tan interiors** (Zonda R, Centenario, Zenvo ST1, Focus RS RX, V12 Zagato ...): for FH3-only shaders the
  converter picks an FH2 shader by name score and keeps FH3's parameters. Leather and plastic (`int_ch2_simplenormalao_glossvar`)
  landed on FH2's *metal* shader `int_m_ch2normglossalphaemissive` without their colour; suede (`fabric_colorlookup`) on
  `int_ch2normglossch1maskdiffuse`, which takes its colour from a texture (tan dash); matmap's "same name" FH2 materials
  carry FH2's colours (`leather_lgl` light grey 0.64 where FH3 is black 0.007).
- `research\fh3port\matlearn.py` pairs FH3 and FH2 library materials of the same name: FH3's interior shaders correspond
  to FH2's `ch1/ch2diffnormglossalpha` family (`int_` variant inside), metals to FH2's `m_` shaders; parameter values
  show the renames (ColorColorParam -> DiffuseColorA/B or DiffuseColorGroup, Gloss -> GlossA/B, F0Vector4 -> F0a/F0b,
  CH1/CH2 diffuse textures -> DiffuseATexture).
- **`matconv.py`** (runs before matmap): every remapped material whose FH3 shader is in `FAMILY` gets that FH2 shader
  (metal when FH3's reflectance >= 0.2 or MetalSwitchBool) and FH3's own values under FH2's names; unknown parameters
  are dropped (shader defaults). matmap now only handles lights, glass, radiosity, badges. Sun strips
  (`car_windsheildbanner`) -> `carpaint_standard` with `CH1DiffuseTextureSwitchBool` on. `paramexpand` renames the same
  parameters in material instances (`_custom` materials: Zenvo seat fabric comes as instance `CH2DiffuseTexture`).
- **Texture swaps**: where FH2 lacks a texture the converter substitutes a similar name (`defaultch1_nrml` -> `eye_nrml`,
  `gascap_018` -> `gascap_001`, `mask_default` -> `led_001_mask`; 125 on the Zonda R). `matconv` restores FH3's texture
  when FH2 can load it: cars\_library (copied by `missing_library_textures`), car files, and global `media\_library`
  textures FH2's own materials use (packed, not on disk - the converter can't see them). FH3-only global textures are
  renamed copies with the same GUID (`ch1_normao_diffopac_nrml_34b98759...` = FH2 `defaultch1_nrml_34b98759...`) and
  resolve to FH2's file. Zonda R: 87 restored.
- **Make logos stretched** (BAC, Alumi Craft): FH2's UI draws a logo over a fixed box - all FH2 logos are 440x376 (L_) or
  220x184. FH3's large logos have their own shape (BAC 400x72). `logos.fit` pads them with transparent BC7 blocks to
  FH2's aspect ratio (no re-encoding); every port run repairs installed ones, `fh3port.py fix-logos` does it alone.
- **In-game check after the full re-port** (Centenario, Zenvo, Zonda logos fine) and the fixes it led to:
  - *Missing rims* (Hoonicorn): FH3 shaders the converter can't place and doesn't report get an empty shader path
    (`Game:\Media\.shaderbin`) - FH2 draws nothing. matconv now converts every material whose shader FH2 doesn't have
    (`ch1_normalpha_color` -> ch1 family, `car_cf_composite_interior` -> `car_cf_interior`). Only the Hoonicorn rim and the
    DB11 carbon had this among ported cars (FH2's own cars ship a few such unused materials).
  - *Dark / black interiors* (RWB 911 seats, Focus RS RX): FH3's `CH2DirectAOSwitchBool` / `CH1LocalAOSwitch0Bool` take
    occlusion from the normal map; FH2's multiply by `AOTexture` / `LocalAOTexture`, default `defaultshader_glos` (dark).
    Converted materials and instances get the switch off when no such texture is set.
  - *Black engine* (Hoonicorn): dual-surface materials (`int_ch1_dualsurface_diffuse`, `_alloptions`) carry a metal and a
    non-metal half; FH2's ch1 shaders have the same halves: `F0_Metal`/`Gloss_Metal` -> `F0a`/`GlossA`,
    `_NonMetal` -> `B` (materials and instances). Metal decision falls back to the file name when FH3 sets no reflectance.
  - *Closed grilles* (Bentayga): FH3's `ext_grille`/`int_grille` cut the holes from the pattern (`FillSwitchBool` 0); FH2
    grilles use the pattern's `_opac` texture as `AlphaTexture` + `CH1OpacityMaskSwitchBool` + alpha test (`TSTA` 1).
  - Restored textures must exist: FH3 references some library textures it ships nowhere (`decorative_00x_opac`,
    `stitch_015` ...) - those keep the converter's stand-in.

## 16. Body-part removal upgrades (2026-10-28)

`bodyparts.py` (called by FH2 Mod Studio's "Body & aero parts / removal"): the shop row (level 4, RequiresGraphics 0,
the car make's part manufacturer) only hides meshes the `.carbin` tags with upgrade row Ids. The Gallardo's wing is
tagged (works), its hood / rear bumper / skirts are always-drawn body meshes (didn't). The script moves the chosen meshes
into the part's upgradable list, tagged with every row Id except the removal rows, and gives rows the `.carbin` doesn't
know (levels added as copies) the models of the nearest known level - otherwise the part vanished at that level (the
Gallardo's level-1 wing copy). Always rebuilt from the saved original `.carbin` (`FH3Port_Backupodyparts`), the zip is
backed up through the journal; FH2 must be closed. `list` / `apply` / `restore` / `make` - see the script's docstring.

