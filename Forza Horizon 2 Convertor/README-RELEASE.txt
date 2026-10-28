====================================================================
 ForzaToolsCli (patched) — standalone release build
 Built: 2026-10-18 | .NET 9, self-contained, single file
====================================================================

WHAT'S IN HERE
  ForzaToolsCli.exe      Windows x64, self-contained (no .NET install needed)
  ForzaToolsCli-linux    Linux x64, self-contained (chmod +x to run)

SOURCE OF TRUTH
  ForzaToolsCli_patched.zip (same download folder) — full patched source
  incl. FixSupport.cs (ZipCdInfo EOCD scanner), FixMaterialsCli.cs
  (fix-materials / audit / manifest-check / manifest-line / selftest /
  test-roundtrip), FixBundles.cs (byte-exact burG bundle r/w), and the
  car-container 1.1 -> 1.0 downgrade pass added 2026-10-18.

VERB STATUS IN THIS BUILD
  WORKING (fully functional, validated against real FH2/FH3 dumps):
    fix-materials    FH3 car zip -> FH2: materialbin conversion, shader
                     remap, MatI rewrite, container downgrades, reports
    audit            enumerate car materials vs FH2 lib/shaders
    manifest-line    print the exact zipmanifest <Zip/> line for a zip
    manifest-check   validate a zip's zipmanifest registration (exit 1
                     on mismatch/missing - catches the Azimuth
                     game+0xfd1927 mount-crash class)
    selftest         offline acceptance (gold-standard byte-identity)
    test-roundtrip   modelbin round-trip check
  STUBBED (no-op in this build - needs the full ForzaTechStudio
  services from your Windows tree):
    convert-car      geometry (carbin/modelbin vertex streams) and
                     TexConv swizzle stages are stubs. fix-materials
                     still runs as the final step and IS real.
    dump-*           diagnostic verbs, minimal support

TYPICAL USAGE
  fix-materials:
    ForzaToolsCli.exe fix-materials --car cars_fh3\LAM_Huracan_15.zip
        --car-name lam_huracan_15
        --fh3-lib fh3_lib --fh2-lib fh2_lib
        --fh2-shaders Shaders.zip
        --out lam_huracan_15.zip --report-dir report
    (libs: FH3 Materials.zip + Materials_pri_44.zip [+ Textures_pri_44.zip]
     in one folder; FH2 Materials.zip in another; FH2 Shaders.zip)
    NOTE: car-owned swatchbins and ManufacturerColors.bin are
    automatically downgraded to FH2-native bundle 1.0 by this build.

  manifest entry for the output zip:
    ForzaToolsCli.exe manifest-line lam_huracan_15.zip
      -> paste the printed <Zip .../> line into game:\media\zipmanifest.xml

  verify registration (after editing the manifest):
    ForzaToolsCli.exe manifest-check lam_huracan_15.zip zipmanifest.xml
      -> must print: MANIFEST OK - registration matches the zip exactly.

  zipmanifest formula (validated on 3,973 real FH2 containers / 608-entry
  real manifest): dirstart = central-directory offset, dirsize = CD size
  + 22 (EOCD record), direntries = entry count; dirstart+dirsize must
  equal the zip's exact file size.
