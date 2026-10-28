"""Time every step of fh3port.convert_zip for one car into a scratch zip (no game files touched).
usage: profile_port.py <FH3 MediaName> <out.zip>"""
import os
import sys
import time

sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import fh3port as P

times = []


def timed(label, fn):
    def w(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            times.append((label, time.perf_counter() - t))
    return w


P.run_cli = timed("ForzaToolsCli fix-materials", P.run_cli)
for mod, fn in (("matmap", "apply"), ("mtpr", "fix_zip"), ("lightparams", "fix_zip"), ("geom", "fix_zip"),
                ("carbin", "fix_zip"), ("aofix", "fix_zip"), ("slod", "fix_zip"), ("zfight", "fix_zip"),
                ("tex", "fix_zip"), ("mncl", "fix_zip")):
    m = getattr(P, mod)
    setattr(m, fn, timed(mod, getattr(m, fn)))
P.fix_vertex_layouts = timed("vlayfix", P.fix_vertex_layouts)
media, out = sys.argv[1], sys.argv[2]
t0 = time.perf_counter()
rc, log, missing = P.convert_zip(os.path.join(P.FH3, "cars", media + ".zip"), media, out)
t1 = time.perf_counter()
extra = P.missing_library_textures(out)
t2 = time.perf_counter()
times.append(("missing_library_textures", t2 - t1))
print("rc", rc, "total convert %.1fs" % (t1 - t0))
for label, s in sorted(times, key=lambda x: -x[1]):
    print("  %-30s %6.1fs" % (label, s))
