# Runs inside IDA. Names the gamedb / SQLite 3.6.19 code path; only replaces auto or vfNN names.
import re
import ida_bytes, ida_name, idc, ida_loader

FLAGS = ida_name.SN_NOWARN | ida_name.SN_NOCHECK | ida_name.SN_FORCE
MECH = re.compile(r"::(off[0-9A-F]+_)?vf[0-9A-F]{2}$")

NAMES = {
    # SQLite 3.6.19 (source id 2009-10-14 c1d499af), statically linked
    0x14007D700: ("sqlite3_openDatabase", "internal openDatabase (registers BINARY/NOCASE/RTRIM)"),
    0x14007D6C0: ("sqlite3_open_v2", "(filename, sqlite3 **ppDb, flags, zVfs)"),
    0x14007E770: ("sqlite3_open", None),
    0x14007E7B0: ("sqlite3_open16", None),
    0x14007E8F0: ("sqlite3_create_collation", "(db, name, enc, ctx, cmp)"),
    0x14003D710: ("sqlite3_prepare_v2", "(db, sql, nBytes=-1, &stmt, &tail)"),
    0x14001EEE0: ("sqlite3_step", "returns 100 SQLITE_ROW / 101 SQLITE_DONE"),
    0x14001AB40: ("sqlite3_finalize", None),
    0x1400203B0: ("sqlite3_column_count", None),
    0x140020840: ("sqlite3_column_name", None),
    0x140020960: ("sqlite3_column_decltype", None),
    0x140020800: ("sqlite3_column_type", None),
    0x1400206E0: ("sqlite3_column_int64", "INTEGER branch of column_type switch"),
    0x140020600: ("sqlite3_column_double", None),
    0x140020690: ("sqlite3_column_text", None),
    0x14003BF30: ("sqlite3InitOne", "builds sqlite_master; 'unsupported file format'"),
    0x14003E740: ("sqlite3RunVacuum", None),
    0x14003E1A0: ("sqlite3_get_table_cb", None),
    0x140035F70: ("sqlite3_attachFunc", "'unable to open database: %s'"),
    0x14005F700: ("sqlite3Pragma", None),
    # Game wrapper
    0x140F4FD10: ("App::App", "sets g_pApp"),
    0x140F52E40: ("App::~App", "clears g_pApp"),
    0x140F64AB0: ("App::Initialize", "opens gamedbRC.slt (or db\\gamedb.slt) -> App+0x40 CDatabase*"),
    0x14108E900: ("Database::CDatabase::Create", "(out ref, std::string path, bool, 0, 0) -> new TRefCountedObjectThreadSafe<CDatabase>"),
    0x14108BCD0: ("Database::CDatabase::CDatabase", None),
    0x14108F720: ("Database::CDatabase::Execute", "vtable slot 8: (this, TReference<IRecordSet>* out, const char* sql); locks this+0x18"),
    0x14108FA20: ("Database::CDatabase::ExecuteUncached", "prepare_v2/step loop on *(this+0x10) building CRecordSet"),
    0x14108CE50: ("Database::CDatabase::ExecuteCached", "prepared-statement cache path (flag this+0x98)"),
    0x141093070: ("Database::CDatabase::Open", "IDatabaseIO slot 0: memory-stream VFS file, sqlite3_open_v2, LOCALIZED_NOCASE, pragmas"),
    0x14108ECA0: ("Database::CDatabase::DisableJournal", "PRAGMA journal_mode = OFF"),
    0x14108F4E0: ("Database::CDatabase::EnableForeignKeys", "PRAGMA foreign_keys = ON"),
    0x141091510: ("Database::CDatabase::AttachAndMergeFileDb", "ATTACH '%s' AS filedb, walks filedb.sqlite_master"),
    0x141094430: ("Database::RegisterMemoryStreamFile", "registers in-memory stream under generated VFS filename"),
    0x1410959D0: ("Database::LocalizedNoCaseCompare", "collation callback for LOCALIZED_NOCASE"),
}

done = 0
for ea, (name, cmt) in NAMES.items():
    cur = ida_name.get_name(ea)
    if ida_bytes.has_dummy_name(ida_bytes.get_flags(ea)) or MECH.search(cur):
        ida_name.set_name(ea, name, FLAGS)
        done += 1
    else:
        print("kept existing name %X %s (wanted %s)" % (ea, cur, name))
    if cmt and not idc.get_func_cmt(ea, 0):
        idc.set_func_cmt(ea, cmt, 0)

ida_name.set_name(0x14354F4F8, "g_pApp", FLAGS)
idc.set_cmt(0x14354F4F8, "App*; +0x40 = CDatabase* (gamedbRC); CDatabase+0x10 = sqlite3*, +0x18 = CRITICAL_SECTION", 1)
ida_loader.save_database(idc.get_idb_path(), 0)
print("named %d functions + g_pApp" % done)
