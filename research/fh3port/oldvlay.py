"""Re-run the FIRST vlayfix rule (any single VDCL mask, fewest added channels) on a pre-vlayfix zip, for comparison.
usage: oldvlay.py <prevlay.zip> <out.zip>"""
import sys, os, struct
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import vlayfix, fh3port


def choose(mask, variants, available):
    best = None
    for f in variants:
        if not f:
            continue
        add, drop = f & ~mask, mask & ~f
        if (add & 0x1F) and not (available & 0x1F) or (add & 0x3E0) and not (available & 0x3E0):
            continue
        key = (bin(add).count("1"), bin(drop).count("1"))
        if best is None or key < best[0]:
            best = (key, f)
    return None if best is None else best[1]


state = {}
# old rule through the new code path: required() returns the chosen variant, or the current mask when it is a variant
orig_parse = vlayfix.parse_vlay
def required(variants):
    mask = state["mask"]
    if mask in variants:
        return mask
    return choose(mask, variants, 0x3FF) or mask
def parse_vlay(b):
    r = orig_parse(b); state["mask"] = r[1]; return r
vlayfix.required = required
vlayfix.parse_vlay = parse_vlay
log = fh3port.fix_vertex_layouts(sys.argv[1], sys.argv[2], "ACU_NSX_16")
print(len(log), "changes")
