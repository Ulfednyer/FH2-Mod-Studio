# FH3 → FH2 port: what crashed the game, and what fixed it

Crash history of the Acura NSX '17 pilot (October 2026), in the order the crashes appeared. The NSX now runs
crash-free, including car meets (user-tested 2026-10-25). Full technical detail is in `README.md` (section numbers
in brackets).

## Crashes and their fixes

| # | Symptom | Cause | Fix (where) | Status |
|---|---|---|---|---|
| 1 | Crash on startup, `game+0xfd1927` (zipmanifest loop) | New zips are invisible: the game only sees files listed in `Mount\hash.manifest`, and Azimuth refuses to start if that file changes | `fh2sql.dll` hooks the game's file-open imports and hands it an extended copy, `<game>\FH3Port\hash.manifest`; the porter registers new files there [2] | Fixed. **Always launch with the DLL injected** |
| 2 | Crash when selecting the car, `game+0x10c9b47` (shader parameter reader) | Material instances nested in `.modelbin` keep FH3 v3 parameters (16-byte GUID after the type byte); FH2 reads v2 | `mtpr.py` rewrites them as v2 [5] | Fixed |
| 3 | Invisible body (not a crash, but a hard failure) | Carbin model entries v16 (FH3) vs v15 (FH2); the extra GUID list shifts every later read | `carbin.py` downgrades v16 → v15 [6b] | Fixed |
| 4 | Crash ~30 s in, `game+0xfd841f` (buffer reader) | vlayfix added VerB/VLay blobs without updating the `Modl` header counts; the loader allocates exactly that many buffer slots and writes past the array | `vlayfix.update_modl_counts`; layouts addressed by position, buffers by Id [8i] | Fixed |
| 5 | Azimuth: `D3D12 graphics pipeline … HRESULT=0x80070057`, input elements with duplicates (`TANGENT0:35 TANGENT0:35`, `TEXCOORD1 ×5`, `TEXCOORD2 TEXCOORD2`) | **Stale blob size fields.** `bundle.serialize` kept each blob's second size field (`usize`) from the original file. Blobs vlayfix rebuilt in place grew, but still declared their old size, so the game read them truncated. `VertexLayout_ReadBlob` (0x1413F2CD0) then reused the previous element's values for the missing ones, and grown vertex buffers lost their tail | `bundle.serialize` writes the real data length into both size fields. FH2 never stores anything else (0 of 71,748 blobs differ) [8n] | **Fixed, user-tested 2026-10-25** |
| 6 | Alumi Craft Class 10 crashes (`game+0xfd841f`, reading 0x7265746e6563 = ASCII "center") | `Blob_IsModelBuffer` (0x1413EEC50) counts **VerB, IndB, MBuf, ConB and Skin** as buffers; `update_modl_counts` counted only the first three. The Class 10's suspension has 4 Skin blobs -> header said 15 buffers, 19 present -> the loader wrote past its buffer array (same crash as #4) | `vlayfix.update_modl_counts` and `modlcounts.py` count all five tags | Fixed 2026-10-25 |
| 7 | Audi #2 Sport quattro S1 crashes Azimuth when its Autoshow preview opens, `game+0x10d72bc` (null material in `MaterialInstance` vf02) | Carbin material overrides (list2: instance name + a serialized material bundle). `Car_ApplyNamedMaterialOverrides` (0x141189830) builds a material from those bytes with `Material_CreateFromBytes` (0x1410CA570); FH3 stores them as burG **1.1** with **v3** parameters, so FH2 gets a null material. 43 of the 214 FH3-only cars have overrides | `carbin.convert_overrides`: 1.1 -> 1.0, v3 -> v2 (`mtpr`), material paths FH2's library lacks pointed at the copy in the car zip. Empty (0-byte) overrides, like the Alumi Craft's rotor caps, stay as they are | Fixed 2026-10-25, needs in-game test |
| 8 | BMW M4 Coupe Horizon Edition (Liberty Walk) crashes when its Autoshow view opens, `game+0x12dcda3` writing 0x8 | `physicsdefinition.bin` is deserialized into a fixed **0x1000-byte** arena (crash dump: arena +0x40 = 0x1000, used 0xE70). The collision reader `sub_1412DCC80` allocates each `PointCloud` with `sub_1412A6670`, which returns NULL when it does not fit, then writes `[NULL+8]`. The M4 HE has four 105-point clouds (needs 7168 bytes); FH2's own cars need at most 4048 (FIA 595SS). 8 ported cars were over: M4 HE, Silvia Spec-R HE, Supervan III, 166MM, Pursuit Ute (+HE), Fairlady Z, HSV GTS Maloo | `physdef.py`: point clouds thinned by farthest-point sampling (axis extremes first) until the need is <= 3968; `batch_port.py check` flags cars over 4048 | Fixed 2026-10-27, needs re-port + in-game test |
| 9 | After fix 8: M4 HE, Supervan III, FH3 458 Italia (`FER_F142_10`) crash on viewing, `game+0x12b04b3` reading 0x94 | `physicsdefinition.bin` trailer = `ChildRenderModelIndices` (read when Version >= 13, `sub_1412DC2F0` -> `sub_1412B0460`): u32 entry count, each entry indexes the definition list. All FH2 cars: 8 zero bytes. 15 FH3 cars have count 4 with 1 definition -> NULL definition (dump: list +0x10 = 1, +0x18 = 4) | `physdef.fix` writes FH2's 8 zero bytes when the count is non-zero; `physdef.check_zip` / `batch_port.py check` flag it | Fixed + 15 cars re-ported 2026-10-27, needs in-game test |

## Attempts that did *not* fix crash 5

They're kept because each one matches FH2's own data more closely, but none of them stopped the crash:

- **Every layout rebuilt to exactly the shader's full vertex-input mask** (no supersets) [8k]: still crashed.
- **Merging duplicate new layouts and dropping unused VerB/VLay blobs** (max 11 layouts / 22 buffers per model,
  FH2 max 10 / 25): ran once without crashing, which was luck. The next session crashed again [8k].
- **Position-only layout (Id -1) moved back to the end**, all other layout Ids = position, as in every FH2 model
  [8m]: still crashed.
- White AO maps for models without one [8j]: no visible effect, harmless.

## Visual problems that turned out to be layout bugs (not crashes)

| Symptom | Cause | Fix |
|---|---|---|
| Lamp units, lamp glass, parts of bumpers black or missing | Meshes didn't supply all vertex inputs of their shader (vlayfix first matched a single depth-pass mask, e.g. `0x1`) | Every mesh gets the union of its shader's VDCL masks [8k] |
| Frames, grilles, lamp housings flat and dark | Invented UV channels kept an identity UV transform instead of the transform of the channel they were copied from | `vlayfix.copy_uv_transforms` [8l] |
| Black / shimmering surfaces, wrong UVs | geom decoded buffers with the wrong layout when several layouts share a stride | Layout taken from the meshes' bindings [8h] |

## Black sticker blocks (not a crash)

Audi S1 #2 / Alumi Craft: sticker sheets drawn as black rectangles that flicker with the paint. FH2 cuts alpha-tested
(`ATST`) materials out only in the depth pre-pass; the colour pass draws wherever the depth matches. FH3 sticker overlays
lie 0.2-0.5 mm above the paint, so their transparent texels (stored black) match too. Fixed by `zfight.py`'s decal pass
(1 mm out, like FH2's own overlays).

## Menu placement (not a crash)

Ported cars showed outside their make in the menus: `Data_Car.MakeName` was plain text ("Alfa Romeo") while FH2
stores the make's DisplayName string id. Now `fix_make_and_bucket` sets MakeName from the make row, matches makes by
ManufacturerCode (FH3 Datsun id 124 is FH2's ROB -> new id) and maps FH3 categories 16/29/41 to FH2 21/21/38.

## Rules a ported model must follow (all checked by the porter's tools)

1. Every new file is listed in the extended `FH3Port\hash.manifest`; the original `Mount\hash.manifest` is never
   changed. Launch with `fh2sql.dll`.
2. Bundle blobs: **size field == usize field == real data length**; header size 4-aligned.
3. `Modl` header counts (meshes, VerB+IndB+MBuf+ConB+Skin, VLay, MatI) equal the blobs present.
4. Layout Id == position, except one position-only layout with Id -1, which is last.
5. Each drawn mesh's layout mask == the union of its FH2 shader's VDCL masks. Missing channels are copied from
   the nearest channel of the same kind, together with that channel's UV transform.
6. Material parameters in FH2 v2 format, names as the FH2 shader expects (`lightparams.py`).
7. Carbin model entries v15.

Checks: `py verify.py <MediaName>`, `research\fh3port\strict.py`, `modlcounts.py`, `superset.py`, `carbin.py check`,
plus a size-field scan (see README 8n).

## Where to look when Azimuth stops

- `amzimuth\data\logs\azimuth.log`: the `graphics pipeline creation refused` line lists the input elements.
  Duplicates mean a malformed layout or a truncated blob.
- The minidumps only contain stacks, not the heap.
- IDA (FH2 `.i64`, functions renamed 2026-10-25): `Model_LoadFromBundle` 0x1413F1D70, `VertexLayout_ReadBlob`
  0x1413F2CD0, `Mesh_BindForDraw` 0x1413F4360, `InputLayoutCache_FindOrCreate` 0x141103BD0,
  `D3DDevice_CreateInputLayout` 0x1410C7BF0.
