# Runs inside IDA. Bytes + file offset of the aaSampleCount default instruction, and the params-getter body.
import ida_bytes, ida_loader, ida_hexrays, idc

ea = 0x140F694E4
size = idc.get_item_size(ea)
print("insn %X size %d bytes %s file_off 0x%X  | %s" % (ea, size, ida_bytes.get_bytes(ea, size).hex(" "),
      ida_loader.get_fileregion_offset(ea), idc.generate_disasm_line(ea, 0)))
print(str(ida_hexrays.decompile(0x140295940)))
