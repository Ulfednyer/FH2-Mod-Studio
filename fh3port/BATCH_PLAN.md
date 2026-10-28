# Plan: port every FH3-only car to FH2

Source list: `FH3_ONLY_CARS.md` (made by `py fh3only.py`, compared with the original FH2 database).

| | Cars |
|---|---|
| FH3 cars FH2 doesn't have | 214 |
| already ported and tested (NSX, Centenario) | 2 |
| **to port** | **212** (3.4 GB of FH3 zips) |
| of these, hidden from FH3's Autoshow (Horizon/Hot Wheels editions `…HE…`, traffic, reward cars) | 51 |
| FH3 zips that can't be ported (no FH3 database row: Porsche pack/DLC, `Shared.zip`; 4 traffic cars whose id is taken in FH2) | 34 |

## Per car: exactly the NSX/Centenario pipeline (`fh3port.py port`, run by `port_car.bat`)

1. ForzaToolsCli `fix-materials` → matmap → mtpr → lightparams.
2. geom (vertex re-encode) → carbin (v16 → v15) → aofix → slod → zfight.
3. vlayfix: exact full VDCL mask per mesh, UV transforms for copied channels, merged duplicate layouts, unused blobs
   dropped, position-only layout last, Modl counts.
4. bundle.serialize: size == usize == data length (the crash fix).
5. tex, mncl; zip installed, `zipmanifest.xml`, extended `FH3Port\hash.manifest`.
6. Database rows; engine sound borrowed from the closest FH2 engine (`fix_engine_audio`); thumbnails; missing
   library textures appended to `Textures.zip`; missing FH3 tyre models converted; suspension XMLs.

## Batches

- **20 cars per batch** (about 11 batches), alphabetical by MediaName. One `port` run per batch (the database is
  written once per run).
- Before each batch: snapshot `gamedbRC.slt`, `zipmanifest.xml`, `FH3Port\hash.manifest`, `Textures.zip` and
  `journal.json` into `FH3Port_Backup\batches\<n>\`, so a bad batch can be rolled back alone (`restore` only knows
  "everything").
- After each batch, automatic checks for every car (a car that fails is rolled out of the batch and logged):
  `verify.py` (zips, CRCs, manifest, physics, database), `strict.py` (layout vs buffer strides), `modlcounts.py`,
  `superset.py` (every drawn mesh exactly its shader's full mask), size-field scan (size == usize), layout order,
  `carbin.py check`, database `integrity_check`.
- Then an in-game test by you: start through Mod Studio, open the Autoshow, look at a few of the new cars, drive
  one, visit a car meet. If Azimuth stops, `azimuth.log` + the batch number tell which batch to inspect.
- Report per batch: ported / failed / engine-sound donor per car.

## Estimates and limits

- Time (measured): test batch 1 took 18 min for 20 cars with the original code. Since then: zfight 5-9x faster
  (byte-identical output), conversions run in parallel (8 workers: 5 cars in 20 s), verify once per round, a car that
  crashes the converter no longer aborts the run. Expected: about 3-5 minutes per batch of 20.
- Disk: about 3.5 GB of new car zips plus the Textures.zip growth and batch snapshots (about 0.7 GB each); 101 GB free.
- Unknown: whether FH2 copes with about 568 cars (354 now) in the Autoshow, garage and AI lists. The batches find
  that limit early.
- Expected rough edges: cars with features the NSX/Centenario don't have (convertibles, open wheel, unusual lights,
  off-road vehicles like the Warthog/trophy trucks, electric motors). Failures get logged and skipped, not forced.

## Test batch 1 result (2026-10-25)

11 of 20 ported and checked (`work/batch_1.md`). 7 failed for real converter/parameter reasons, listed in
`failed_cars.json` and skipped by later batches (`batch_port.py` leaves them out; fix the porter, then retry them).
The 2 Bentleys only missed batch 1 because of the crash and come next.

## Afterwards

- The friends pack can be rebuilt from the journal with all ported cars (size grows with every car).
- `FH3_ONLY_CARS.md` gets a status column update (`ported` / `failed: reason`).
