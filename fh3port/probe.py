"""Registers / removes a tiny new zip (media\\cars\\fh3probe.zip) to observe how the game opens files that are not
in the original package. Uses fh3port's journal, so 'fh3port.py restore' undoes it."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fh3port as P

PROBE = os.path.join(P.FH2, "cars", "fh3probe.zip")

if __name__ == "__main__":
    j = P.journal()
    if len(sys.argv) > 1 and sys.argv[1] == "index":
        # the probe was created before hash.manifest support: register it now
        P.hm_register(j, PROBE)
        P.save_journal(j)
        print("indexed", PROBE, "value", j.get("hash_manifest"))
    elif len(sys.argv) > 1 and sys.argv[1] == "add":
        P.touch(j, PROBE)
        P.write_native_zip(PROBE, [P._entry_from_bytes("probe.txt", b"fh3port probe\n")])
        P.manifest_set(j, PROBE)
        print("registered", PROBE)
    else:
        print(__doc__)
