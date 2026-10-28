"""Zip writing for the conversion stages.

convert_zip runs ~18 stages, each reading the car zip and writing a complete new one. Writing every stage's zip
deflate-compressed re-compressed every texture ~18 times: 40% of a car's conversion time. While FAST is on (only
inside fh3port.convert_zip) the stages write their zips stored (uncompressed, also faster to read back) and the
finished zip is compressed once by finish(). With FAST off (standalone tools) zips are deflated as before.
"""
import copy
import os
import zipfile

FAST = False


class Writer(zipfile.ZipFile):
    def writestr(self, zinfo_or_arcname, data, compress_type=None, compresslevel=None):
        if FAST:
            if isinstance(zinfo_or_arcname, zipfile.ZipInfo):
                zinfo_or_arcname = copy.copy(zinfo_or_arcname)   # keeps the source entry's name, date, attributes
                zinfo_or_arcname.compress_type = zipfile.ZIP_STORED
            compress_type = zipfile.ZIP_STORED
        return super().writestr(zinfo_or_arcname, data, compress_type, compresslevel)


def writer(path):
    """ZipFile for a stage's output (use like zipfile.ZipFile(path, "w", ZIP_DEFLATED))."""
    return Writer(path, "w", zipfile.ZIP_STORED if FAST else zipfile.ZIP_DEFLATED)


def finish(path):
    """Deflates every entry of a zip written in FAST mode (once, at the end of a conversion)."""
    tmp = path + ".deflate.zip"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            out = copy.copy(info)
            out.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(out, zin.read(info))
    os.replace(tmp, path)
