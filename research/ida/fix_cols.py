import ida_name, idc, ida_loader

FLAGS = ida_name.SN_NOWARN | ida_name.SN_NOCHECK | ida_name.SN_FORCE
# order matches sqlite 3.6.19 vdbeapi.c; temp names first to avoid clashing with the swapped pair
for ea in (0x140020690, 0x1400206E0):
    ida_name.set_name(ea, "tmp_%X" % ea, FLAGS)
NAMES = {
    0x140020430: "sqlite3_column_blob", 0x140020580: "sqlite3_column_bytes", 0x1400205C0: "sqlite3_column_bytes16",
    0x140020650: "sqlite3_column_int", 0x140020690: "sqlite3_column_int64", 0x1400206E0: "sqlite3_column_text",
    0x140020730: "sqlite3_column_value", 0x1400207B0: "sqlite3_column_text16", 0x140020480: "sqlite3_columnMem",
    0x14001E760: "sqlite3_value_text", 0x14001E800: "sqlite3_value_type", 0x14007B5A0: "sqlite3ErrStr",
    0x14007D3F0: "sqlite3_errmsg", 0x14007D490: "sqlite3_errmsg16",
}
for ea, n in NAMES.items():
    ida_name.set_name(ea, n, FLAGS)
idc.set_func_cmt(0x1400206E0, "", 0)
idc.set_func_cmt(0x140020690, "", 0)
ida_loader.save_database(idc.get_idb_path(), 0)
print("renamed %d" % len(NAMES))
