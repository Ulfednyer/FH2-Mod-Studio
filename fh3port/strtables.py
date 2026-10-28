"""Car and make names in FH2's string tables (media\\stripped\\stringtables\\<LANG>.zip, one .str per database table).

The pause and race menus look names up by string id; plain text in Data_Car (what the porter wrote before) only shows
in the Autoshow. A string id is "_&<n>" with n = (table hash << 16) | key: the high 16 bits pick the table
(CStringTableManager::vf01 0x141245740 hashes each .str name), the low 16 bits are the key inside it. Data_Car's ids
all carry 0xCD49, List_CarMake's 0x3323 (read from FH2's own rows, not computed).

.str layout (LSB2, reader sub_141246F30): 24-byte header "LSB2", flags (bit 0 clear), byte 9 = 2, u32 @12 = offset of
the string section, u32 @16 = section count, u32[] @20 = section offsets. The game reads only section 0:
u32 size (whole section) | u32 count | (count + 1) x (u16 key, u32 offset in UTF-16 units), sorted by key, the last
one a 0xFFFF sentinel holding the pool length | UTF-16 pool, NUL-terminated strings, one extra NUL. Section 1 (debug
IDS_ names), 2 (tool comment) and 3 (keys in original order) are carried over unchanged.

Names come from FH3's string table of the same language (FH3 ids are 64-bit; its tables are keyed by the low 32 bits),
English FH3 text where a language has none.
"""
import os
import struct
import zipfile

LANGS = ["br", "CHT", "cz", "DE", "DEV", "EN", "ES", "FR", "GB", "HU", "IT", "JP", "KO", "LOC", "MX", "nl", "PL", "RU"]


class Lsb2:
    def __init__(self, d):
        if d[:4] != b"LSB2" or d[4] & 1 or d[9] != 2:
            raise ValueError("not an LSB2 string table")
        self.head = bytearray(d[:12])
        self.sec0 = struct.unpack_from("<I", d, 12)[0]
        n = struct.unpack_from("<I", d, 16)[0]
        self.offs = list(struct.unpack_from("<%dI" % n, d, 20))
        if self.offs[0] != self.sec0:
            raise ValueError("string section is not the first section")
        size, count = struct.unpack_from("<II", d, self.sec0)
        ents = [struct.unpack_from("<HI", d, self.sec0 + 8 + 6 * i) for i in range(count + 1)]
        pool = self.sec0 + 8 + 6 * (count + 1)
        self.strings = {}
        for k, o in ents[:-1]:
            p = pool + 2 * o
            e = p
            while e + 1 < len(d) and (d[e] or d[e + 1]):
                e += 2
            self.strings[k] = d[p:e].decode("utf-16-le", "replace")
        self.rest = d[self.sec0 + size:]          # sections 1.. as they are
        self.gap = d[20 + 4 * n:self.sec0]          # bytes between the header and section 0 (none in FH2's files)

    def keys(self):
        return set(self.strings)

    def build(self):
        keys = sorted(self.strings)
        ents, pool, o = bytearray(), bytearray(), 0
        for k in keys:
            s = self.strings[k].encode("utf-16-le") + b"\x00\x00"
            ents += struct.pack("<HI", k, o)
            pool += s
            o += len(s) // 2
        ents += struct.pack("<HI", 0xFFFF, o)
        pool += b"\x00\x00"
        sec0 = struct.pack("<II", 8 + len(ents) + len(pool), len(keys)) + ents + pool
        delta = len(sec0) - (self.offs[1] - self.offs[0] if len(self.offs) > 1 else len(sec0))
        offs = [self.offs[0]] + [x + delta for x in self.offs[1:]]
        head = bytes(self.head) + struct.pack("<II", self.sec0, len(offs)) + struct.pack("<%dI" % len(offs), *offs)
        return head + self.gap + sec0 + self.rest


class Fh3Lang:
    """One FH3 language zip: table name -> {low 32 bits of the id: text}."""
    def __init__(self, path):
        self.z = zipfile.ZipFile(path) if os.path.exists(path) else None
        self.names = {n.lower(): n for n in self.z.namelist()} if self.z else {}
        self.cache = {}

    def table(self, name):
        name = name.lower() + ".str"
        if name not in self.cache:
            m = {}
            n = self.names.get(name)
            if n:
                d = self.z.read(n)
                cnt = struct.unpack_from("<I", d, 20)[0]
                pool = 24 + cnt * 8
                for i in range(cnt):
                    k, o = struct.unpack_from("<II", d, 24 + i * 8)
                    p = e = pool + o
                    while e + 1 < len(d) and (d[e] or d[e + 1]):
                        e += 2
                    m[k] = d[p:e].decode("utf-16le", "replace")
            self.cache[name] = m
        return self.cache[name]

    def text(self, table, value):
        if not isinstance(value, str) or not value.startswith("_&"):
            return None
        try:
            return self.table(table).get(int(value[2:]) & 0xFFFFFFFF)
        except ValueError:
            return None


def table_hash(db, table, column):
    """High 16 bits FH2's own string ids of a table carry (Data_Car 0xCD49, List_CarMake 0x3323)."""
    import collections
    c = collections.Counter()
    for (v,) in db.execute('SELECT "%s" FROM "%s"' % (column, table)):
        if isinstance(v, str) and v.startswith("_&") and v[2:].isdigit() and int(v[2:]) < 1 << 32:
            c[int(v[2:]) >> 16] += 1
    return c.most_common(1)[0][0] if c else None


class Names:
    """Collects names to write: (fh2 table, fh3 string id, english fallback) -> FH2 "_&" id; then writes every
    language zip. Keys are kept per FH3 id in the journal (j["strings"]) so a re-port reuses them."""

    def __init__(self, j, db, fh2_tables_dir, fh3_tables_dir):
        self.j, self.db = j, db
        self.dir2, self.dir3 = fh2_tables_dir, fh3_tables_dir
        self.reg = j.setdefault("strings", {})
        self.todo = {}                      # (table, key) -> {lang: text}
        self.hash = {"Data_Car": table_hash(db, "Data_Car", "DisplayName"),
                     "List_CarMake": table_hash(db, "List_CarMake", "DisplayName")}
        self.fh3 = {lang: Fh3Lang(os.path.join(fh3_tables_dir, lang.lower() + ".zip")) for lang in LANGS}
        self.used = {}

    def _used(self, table):
        if table not in self.used:
            keys = set()
            for lang in LANGS:
                zp = os.path.join(self.dir2, lang + ".zip")
                if not os.path.exists(zp):
                    continue
                with zipfile.ZipFile(zp) as z:
                    n = next((x for x in z.namelist() if x.lower() == table.lower() + ".str"), None)
                    if n:
                        keys |= Lsb2(z.read(n)).keys()
            self.used[table] = keys
        return self.used[table]

    def id_for(self, table, fh3_value, fallback):
        """FH2 string id ("_&n") for an FH3 string id; None when FH3 has no text for it in any language."""
        if not isinstance(fh3_value, str) or not fh3_value.startswith("_&") or self.hash.get(table) is None:
            return None
        texts = {}
        en = self.fh3["EN"].text(table, fh3_value) or fallback
        for lang in LANGS:
            texts[lang] = self.fh3[lang].text(table, fh3_value) or en
        if not en:
            return None
        reg = self.reg.setdefault(table, {})
        low = str(int(fh3_value[2:]) & 0xFFFFFFFF)
        key = reg.get(low)
        if key is None:
            taken = self._used(table) | set(reg.values())
            key = int(low) & 0xFFFF
            while key in taken or key in (0, 0xFFFF):
                key = (key + 1) & 0xFFFF
            reg[low] = key
        self.todo[(table, key)] = texts
        return "_&%d" % ((self.hash[table] << 16) | key)

    def write(self, install):
        """Rewrites every language zip that needs entries; install(tmp_zip, dest) puts it in place."""
        if not self.todo:
            return 0
        n = 0
        for lang in LANGS:
            zp = os.path.join(self.dir2, lang + ".zip")
            if not os.path.exists(zp):
                continue
            with zipfile.ZipFile(zp) as z:
                infos = z.infolist()
                files = {i.filename: z.read(i) for i in infos}
            changed = False
            for table in {t for t, _ in self.todo}:
                name = next((x for x in files if x.lower() == table.lower() + ".str"), None)
                if not name:
                    continue
                t = Lsb2(files[name])
                for (tb, key), texts in self.todo.items():
                    if tb == table and t.strings.get(key) != texts[lang]:
                        t.strings[key] = texts[lang]
                        changed = True
                files[name] = t.build()
            if changed:
                tmp = zp + ".names.tmp"
                with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
                    for i in infos:
                        zo.writestr(i.filename, files[i.filename])
                install(tmp, zp)
                os.remove(tmp)
                n += 1
        return n
