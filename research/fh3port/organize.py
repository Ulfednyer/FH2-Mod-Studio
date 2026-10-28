import os, re, shutil
S = r"C:\Users\opsuc\AppData\Local\Temp\claude\C--Users-opsuc-Downloads-Anthem-1-0-0-64-x64--8wekyb3d8bbwe\b21eefe5-12ef-45fd-acc2-f5d692c5553e\scratchpad"
R = r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\research"
groups = {
    "fh3port": r"^(bundle_extract|cli_inv|checks|dbcmp|deps2?|dump\d?|exestr|gaps|geomtest|hmcheck|hmvalues|issues|lookups|matdump|mdltags|meshdiff2?|meshfields|rawdisp|scalecheck|strfmt|strparse3?|swtest|tails|tangent2?|verify_pilot|vlay_inv|align|organize)\.py$",
    "ida": r"^(ida|ida_.*|aa_.*|dec(_\w)?|callees|grep_dec|survey_c_\d|rtti_rename|inspect_rtti|find_\w+|cforza|scan_frame|render2|render_strings|shadow_use|framerate|farclip|mblur|quality|dxbc_ms|cmdsrc|peek|snap|split|worklist|name_db|name_dist|db_ctx|colmap|fix_cols|fix_folded|apply)\.py$",
    "modstudio": r"^(addtest\d?|spacertest|cartest|carapply|undotest|page|shot)\.ps1$|^(levels|upgrades|z06|rims|track|carbin|parts)\.py$|^bodytest\.sql$",
}
moved = {}
for f in sorted(os.listdir(S)):
    p = os.path.join(S, f)
    if not os.path.isfile(p) or not f.endswith((".py", ".ps1", ".sql")):
        continue
    dest = next((g for g, pat in groups.items() if re.match(pat, f)), "misc")
    os.makedirs(os.path.join(R, dest), exist_ok=True)
    shutil.move(p, os.path.join(R, dest, f))
    moved.setdefault(dest, []).append(f)
# the .NET metadata dumper (source only)
src = os.path.join(S, "mddump")
if os.path.isdir(src):
    dst = os.path.join(R, "fh3port", "mddump")
    os.makedirs(dst, exist_ok=True)
    for f in ("Program.cs", "mddump.csproj"):
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    moved.setdefault("fh3port", []).append("mddump/ (Program.cs, mddump.csproj)")
for g, fs in moved.items():
    print("%-10s %3d  %s" % (g, len(fs), ", ".join(fs[:12]) + (" ..." if len(fs) > 12 else "")))
