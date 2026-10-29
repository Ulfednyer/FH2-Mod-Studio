"""In-game bisection of an FH1 port against its donor: put the donor's original files back for a chosen subset of the
entries that differ, so one game test tells whether the problem is inside that subset.

    py donorswap.py save    <car zip>                       keep the current (FH1) zip as <work>\\<car>.fh1.zip (once)
    py donorswap.py list    <car zip> <donor zip> <car> <donor>       entries that differ from the donor (numbered)
    py donorswap.py donor   <car zip> <donor zip> <car> <donor> <i,j-k|all>   install donor versions of those entries
    py donorswap.py restore <car zip>                       put the saved FH1 zip back
FH2 must be closed; writes go through the porter journal (manifest kept in sync).
"""
import os
import shutil
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "..", "fh3port")))
import fh3port

WORK = os.path.join(fh3port.WORK, "fh1")


def saved(zp):
    return os.path.join(WORK, os.path.splitext(os.path.basename(zp))[0] + ".fh1.zip")


def differing(zp, donor_zp, car, donor):
    """[(entry in car zip, entry in donor zip)] whose bytes differ (FH1 copy of the original zip, if saved)."""
    src = saved(zp) if os.path.exists(saved(zp)) else zp
    out = []
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(donor_zp) as b:
        bn = {n.lower().replace(donor.lower(), car.lower()): n for n in b.namelist()}
        for n in a.namelist():
            k = n.lower()
            if k in bn and a.read(n) != b.read(bn[k]):
                out.append((n, bn[k]))
    return sorted(out)


def pick(spec, n):
    if spec == "all":
        return list(range(n))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def main(cmd, zp, *rest):
    if cmd == "save":
        os.makedirs(WORK, exist_ok=True)
        if not os.path.exists(saved(zp)):
            shutil.copy2(zp, saved(zp))
        print("saved", saved(zp))
    elif cmd == "restore":
        j = fh3port.journal()
        with zipfile.ZipFile(saved(zp)) as z:
            files = {n: z.read(n) for n in z.namelist()}
        fh3port.replace_in_zip(j, zp, files)
        fh3port.save_journal(j)
        print("restored FH1 version (%d entries)" % len(files))
    else:
        donor_zp, car, donor = rest[:3]
        diffs = differing(zp, donor_zp, car, donor)
        if cmd == "list":
            for i, (n, _) in enumerate(diffs):
                print("%3d %s" % (i, n))
            return
        if not os.path.exists(saved(zp)):
            sys.exit("run save first")
        chosen = [diffs[i] for i in pick(rest[3], len(diffs))]
        # start from the FH1 version, then swap the chosen entries
        with zipfile.ZipFile(saved(zp)) as a, zipfile.ZipFile(donor_zp) as b:
            files = {n: a.read(n) for n in a.namelist()}
            for n, dn in chosen:
                files[n] = b.read(dn)
        j = fh3port.journal()
        fh3port.replace_in_zip(j, zp, files)
        fh3port.save_journal(j)
        print("donor versions installed for %d entries:" % len(chosen))
        for n, _ in chosen:
            print("   ", n)


if __name__ == "__main__":
    main(*sys.argv[1:])
