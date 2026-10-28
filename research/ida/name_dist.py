import ida_bytes, ida_name, idc, ida_loader

FLAGS = ida_name.SN_NOWARN | ida_name.SN_NOCHECK | ida_name.SN_FORCE
NAMES = {
    0x141144320: ("TrackSettings::Serialize", "tracksettings.xml; this = CTrackPresentation+0x8110. ShadowNear+0x230 InGameShadowEnd+0x234 TrackSegCamShadowEnd+0x238 GrassFadeStart+0x164 End+0x168 GrassLODDist+0x358 CollidableDropDistance+0x32C Cubemap MeshLimit+0x2C8 FarDistance+0x2D4 Crowds Sprite+0x400 Visible+0x404 Shadow+0x408 Model+0x40C DepthFadeStart+0x410 FogEnd+0x8E8 LODGroups+0xA8"),
    0x14134AF90: ("CTrackPresentation::SerializeTrackSettings", "vtable slot 143"),
    0x14130B290: ("DynamicRenderCarLODTransDist::Serialize", "near +0 far +4 veryfar +8 farthest +0xC (control+8)"),
    0x140F694E4: (None, "aaSampleCount default (4) + aaQuality (0)"),
    0x1434AF7D0: ("g_AppCommandLineParameters", "+0x2608 aaSampleCount, +0x260C aaQuality"),
    0x140295940: ("GetAppCommandLineParameters", None),
    0x141083620: ("CmdLine_GetInt", "matches 'name=value' (case-insensitive), supports K/M suffix"),
    0x1410EF2F0: (None, "Frame::Init(width, height, ?, DXGI_SAMPLE_DESC) -> stored at this+0x10"),
}
for ea, (name, cmt) in NAMES.items():
    if name and (ida_bytes.has_dummy_name(ida_bytes.get_flags(ea)) or "::vf" in ida_name.get_name(ea)):
        ida_name.set_name(ea, name, FLAGS)
    if cmt:
        if idc.get_func_attr(ea, idc.FUNCATTR_START) == ea:
            idc.set_func_cmt(ea, cmt, 0)
        else:
            idc.set_cmt(ea, cmt, 1)
ida_loader.save_database(idc.get_idb_path(), 0)
print("done")
