import ida_name, idc, ida_loader
ea = 0x141008720
ida_name.set_name(ea, "folded_ReturnFloatAt0xC", ida_name.SN_NOWARN | ida_name.SN_FORCE)
idc.set_func_cmt(ea, "ICF-folded getter (return *(float*)(this+0xC)); shared by PhysicsModulationFunctionBase family, CCarDynamics, TCatchup<float>, Replay::CReplayStream", 0)
ida_loader.save_database(idc.get_idb_path(), 0)
print(ida_name.get_name(ea))
