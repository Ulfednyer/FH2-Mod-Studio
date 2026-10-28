import ida_kernwin, ida_loader
s = ida_loader.snapshot_t()
s.desc = "before rtti_rename"
print(ida_kernwin.take_database_snapshot(s))
