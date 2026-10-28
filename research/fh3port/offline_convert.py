"""Convert FH3 cars with the porter's parallel job runner into a scratch folder (no game files touched); prints rc /
failure reason per car and the wall time. Optionally compares modelbins with the installed zips.
usage: offline_convert.py <out_dir> <MediaName>... [--compare]"""
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import fh3port as P


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_dir, cars = args[0], args[1:]
    os.makedirs(out_dir, exist_ok=True)
    jobs = [(os.path.join(P.FH3, "cars", m + ".zip"), m, os.path.join(out_dir, m + ".zip"), False) for m in cars]
    t = time.perf_counter()
    with ProcessPoolExecutor(min(P.CONVERT_WORKERS, len(jobs))) as ex:
        res = list(ex.map(P._convert_job, jobs))
    print("%d cars, %d workers, %.1f s wall" % (len(jobs), min(P.CONVERT_WORKERS, len(jobs)), time.perf_counter() - t))
    for (src, m, out, _), (rc, log, missing, extra, err) in zip(jobs, res):
        errs = [l.strip() for l in log.splitlines() if "error" in l.lower() or "exception" in l.lower()]
        reason = err.strip().splitlines()[-1] if err else ("" if rc == 0 else (errs[0] if errs else (log.strip().splitlines()[-1] if log.strip() else "rc %s" % rc)))
        print("  %-28s %s" % (m, "ok" if rc == 0 and not err else "FAILED: " + reason[:200]))
        if "--compare" in sys.argv and rc == 0 and os.path.exists(os.path.join(P.FH2, "cars", m + ".zip")):
            inst = os.path.join(P.FH2, "cars", m + ".zip")
            a, b = zipfile.ZipFile(out), zipfile.ZipFile(inst)
            names = [n for n in a.namelist() if n.lower().endswith(".modelbin")]
            same = sum(a.read(n) == b.read(n) for n in names)
            print("      modelbins identical to installed: %d of %d" % (same, len(names)))


if __name__ == "__main__":
    main()
