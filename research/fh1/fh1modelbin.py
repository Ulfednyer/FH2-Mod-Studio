"""
FH1 -> FH2 Modelbin Generator.
Converts FH1 / FM4 Xbox 360 carbin geometry into native FH2 burG 1.0 .modelbin bundles.
"""

import copy
import os
import struct
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_FH3PORT = os.path.normpath(os.path.join(_HERE, "..", "..", "fh3port"))
if _FH3PORT not in sys.path:
    sys.path.insert(0, _FH3PORT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import bundle
import vlayfix
import geom
import fh1carbin as carbin

MATERIAL_MAP = {
    "carpaint": "carpaint",
    "body": "carpaint",
    "body_2": "carpaint",
    "carbon_fiber": "carbonfiber_001",
    "carbonfiber": "carbonfiber_001",
    "chrome": "chrome_polished",
    "chrome_satin": "chrome_satin",
    "chrome_satin001": "chrome_satin",
    "black": "blkplastic_mgl",
    "black_matte": "blkplastic_mgl",
    "matte_black": "blkplastic_mgl",
    "plastic": "blkplastic_mgl",
    "plastic2": "blkplastic_mgl",
    "bump_plastic": "blkplastic_mgl",
    "grilleplastic": "grilleplastic_002",
    "grille1": "grilleplastic_002",
    "grille1_alpha": "grilleplastic_002",
    "rubber": "rubber_smooth",
    "rubber_trim": "rubber_smooth",
    "weatherstrip": "blkweatherstrip_001",
    "glass": "gls_tint_001",
    "black_glass": "blackglass",
    "window": "gls_window",
    "lights_glass": "gls_clear",
    "tail_light": "gls_red",
    "tail_light_lod0": "gls_red",
    "taillight2s": "gls_red",
    "reverse_light": "gls_clear",
    "reverse_light_lod0": "gls_clear",
    "textured_reflector": "reflector_001",
    "reflector": "reflector_001",
    "detail_glass_red": "gls_red",
    "head_light": "gls_clear",
    "oldhead": "gls_clear",
    "fullbeam": "gls_lightbulb",
    "xenonhead": "gls_projector",
    "drlwhite": "gls_ledbulb_round",
    "indicator_left": "gls_amber",
    "indicator_right": "gls_amber",
    "drlorange": "gls_amber",
    "steel": "steel",
    "metal": "steel",
    "frame": "frame",
    "leather": "blkleather_bump_mgl",
    "bump_leather": "blkleather_bump_mgl",
    "cloth": "blkleather_bump_lgl",
    "headliner": "blkleather_bump_lgl",
    "badge": "badges/acu_emblem_001",
    "emblem": "badges/acu_emblem_001",
    "wood": "aluminum_machined",
    "solid": "steel",
    "mirrorleft": "gls_wingmirror_001",
    "mirrorright": "gls_wingmirror_001",
    "mirrormiddle": "gls_wingmirror_001",
    "undercarriage": "blkplastic_mgl",
    "bottom": "blkplastic_mgl",
    "misc": "blkplastic_mgl",
    "matte_colors": "blkplastic_mgl",
    "race_kit_red": "carpaint",
    "numplate": "carpaint",
    "inner_rim": "aluminum_machined",
    "outer_rim": "chrome_polished",
    "rim": "aluminum_machined",
    "wheel_black": "blkplastic_mgl",
    "blur_rim": "wheel_blur",
    "blur_lip": "wheel_blur",
    "bump_stitching": "stitch_001",
    "gauge_emissive": "blkplastic_mgl",
    "gauge_needle": "gls_red",
    "z_gauge_emissive_alpha": "blkplastic_mgl",
    "digital_gauge": "blkplastic_mgl",
    "mottled": "blkplastic_mgl",
}


def map_material(fh1_mat: str) -> str:
    mat = fh1_mat.lower().strip()
    return MATERIAL_MAP.get(mat, "carpaint")


def combine_parts(parts: List[carbin.FH1Part], new_name: str) -> carbin.FH1Part:
    """Combines multiple FH1Part objects into a single FH1Part."""
    if not parts:
        raise ValueError("No parts to combine")
    first = parts[0]
    combined = carbin.FH1Part(new_name, first.origin, first.min_box.copy(), first.max_box.copy())

    pos_list = []
    norm_list = []
    tan_list = []
    uv0_list = []
    uv1_list = []
    v_offset = 0

    all_min = []
    all_max = []

    for p in parts:
        pos_list.append(p.positions)
        norm_list.append(p.normals)
        tan_list.append(p.tangents)
        uv0_list.append(p.uv0)
        uv1_list.append(p.uv1)
        all_min.append(p.origin + p.min_box)
        all_max.append(p.origin + p.max_box)

        for m in p.meshes:
            if m.triangle_count == 0:
                continue
            new_tris = m.triangles + v_offset
            combined.meshes.append(carbin.FH1Mesh(m.shader, new_tris, m.raw_indices, m.index_size))

        v_offset += len(p.positions)

    combined.positions = np.concatenate(pos_list, axis=0)
    combined.normals = np.concatenate(norm_list, axis=0)
    combined.tangents = np.concatenate(tan_list, axis=0)
    combined.uv0 = np.concatenate(uv0_list, axis=0)
    combined.uv1 = np.concatenate(uv1_list, axis=0)

    glb_min = np.min(all_min, axis=0)
    glb_max = np.max(all_max, axis=0)
    combined.origin = (glb_min + glb_max) / 2.0
    combined.min_box = glb_min - combined.origin
    combined.max_box = glb_max - combined.origin

    return combined


def make_mati_blob(mat_id: int, mat_name: str) -> bundle.Blob:
    """Creates an FH2 MatI blob referencing a library material."""
    if mat_name.startswith("badges/"):
        rel_path = f"Game:\\Media\\cars\\_library\\materials\\{mat_name}.materialbin"
    else:
        rel_path = f"Game:\\Media\\cars\\_library\\materials\\basematerials\\{mat_name}.materialbin"
    mati_data = bytes([len(rel_path)]) + rel_path.encode("latin1")

    b_mati = bundle.Blob(b"ITAM", (1, 0), [(b"emaN", 0, mat_name.encode("latin1")), (b"TSTA", 1, b"\x00")], mati_data)
    b_mtpr = bundle.Blob(b"RPTM", (2, 0), [], b"\x00" * 13)
    inner_data = bundle.serialize([b_mati, b_mtpr])

    meta_name = mat_name.encode("latin1")
    meta_id = struct.pack("<i", mat_id)
    return bundle.Blob(b"ItaM", (1, 0), [(b"emaN", 0, meta_name), (b"  dI", 0, meta_id)], inner_data)


def make_vlay_blobs():
    """Returns (VLay_main, VLay_shadow)."""
    sems = ["POSITION", "NORMAL", "TEXCOORD", "TANGENT"]
    res = bytearray(struct.pack("<H", len(sems)))
    for s in sems:
        res += struct.pack("<I", len(s)) + s.encode("latin1")

    elements = [
        (0, 0, 0, 6, -1, 0, 3),    # POSITION slot 0
        (1, 0, 1, 10, -1, 0, 9),   # NORMAL slot 1, off -1
        (2, 0, 1, 35, -1, 0, 46),  # TEXCOORD0 slot 1, off -1
        (2, 1, 1, 35, -1, 0, 46),  # TEXCOORD1 slot 1, off -1
        (2, 2, 1, 35, -1, 0, 46),  # TEXCOORD2 slot 1, off -1
        (2, 3, 1, 35, -1, 0, 46),  # TEXCOORD3 slot 1, off -1
        (3, 0, 1, 10, -1, 0, 9),   # TANGENT0 slot 1, off -1
        (3, 1, 1, 10, -1, 0, 9),   # TANGENT1 slot 1, off -1
    ]
    res += struct.pack("<H", len(elements))
    for el in elements:
        res += struct.pack("<HHIIiI", el[0], el[1], el[2], el[3], el[4], el[5])
    for el in elements:
        res += struct.pack("<I", el[6])
    mask = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 5) | (1 << 6)
    res += struct.pack("<I", mask)

    b_main = bundle.Blob(b"yaLV", (1, 1), [(b"  dI", 0, struct.pack("<i", 0))], bytes(res))

    res_sh = bytearray(struct.pack("<H", 1))
    res_sh += struct.pack("<I", 8) + b"POSITION"
    res_sh += struct.pack("<H", 1)
    res_sh += struct.pack("<HHIIiI", 0, 0, 0, 6, 0, 0)
    res_sh += struct.pack("<I", 3)
    res_sh += struct.pack("<I", 0)
    b_shadow = bundle.Blob(b"yaLV", (1, 1), [(b"  dI", 0, struct.pack("<i", -1))], bytes(res_sh))

    return b_main, b_shadow


def uv_transform(uv: np.ndarray):
    """(offset, scale) per axis so that uv = offset + unorm16 * scale covers the channel's range."""
    if len(uv) == 0:
        return np.zeros(2), np.ones(2)
    lo, hi = uv.min(axis=0).astype(np.float64), uv.max(axis=0).astype(np.float64)
    scale = hi - lo
    scale[scale < 1e-8] = 1.0
    return lo, scale


def encode_uv(uv: np.ndarray, xf) -> np.ndarray:
    off, scale = xf
    return np.clip(np.round((uv - off) / scale * 65535.0), 0, 65535).astype(np.uint16)


def uv_tail(xfs) -> bytes:
    """Mesh >= 1.5 tail: 5 UV transforms (offset.x, scale.x, offset.y, scale.y), one per TEXCOORD0..4. The layout declares
    TEXCOORDs R16G16_UNORM (dxgi 35), so FH2 computes uv = offset + unorm * scale; zero scales made every UV 0."""
    out = b""
    for k in range(5):
        off, scale = xfs[k] if k < len(xfs) else (np.zeros(2), np.ones(2))
        out += struct.pack("<4f", off[0], scale[0], off[1], scale[1])
    return out


def to_fh2_axes(part: carbin.FH1Part) -> carbin.FH1Part:
    """FH1 cars face -z (right-handed), FH2 cars +z (left-handed; x = right in both): the donor's front bumper spans
    z 1.43..2.23, FH1's -2.22..-1.43. Mirror z of positions, normals and tangents and reverse the triangle winding;
    unconverted, every FH1 part sat back to front in the donor's car."""
    flip = np.array([1.0, 1.0, -1.0])
    p = copy.copy(part)
    p.positions = part.positions * flip
    p.normals = part.normals.copy()
    p.normals[:, 2] *= -1
    p.tangents = part.tangents.copy()
    p.tangents[:, 2] *= -1
    p.origin = part.origin * flip
    p.min_box = np.array([part.min_box[0], part.min_box[1], -part.max_box[2]])
    p.max_box = np.array([part.max_box[0], part.max_box[1], -part.min_box[2]])
    p.meshes = [carbin.FH1Mesh(m.shader, m.triangles[:, [0, 2, 1]], m.raw_indices, m.index_size) for m in part.meshes]
    return p


def make_verb_blobs(positions: np.ndarray, normals: np.ndarray, tangents: np.ndarray, uv0: np.ndarray, uv1: np.ndarray, uv_xfs=None, bitan_sign: float = 1.0):
    """Creates VerB -1 (Positions) and VerB 0 (Attributes). uv_xfs: [(offset, scale)] for TEXCOORD0/1 (uv_transform).
    bitan_sign -1 for mirrored geometry: cross(n, t) of mirrored vectors is minus the mirrored bitangent."""
    n = len(positions)

    # VerB -1: Positions (stride 12, dxgi 6)
    pos_data = bytearray(struct.pack("<IIHHI", n, n * 12, 12, 1, 6))
    pos_data += positions.astype(np.float32).tobytes()
    b_pos = bundle.Blob(b"BreV", (1, 0), [(b"  dI", 0, struct.pack("<i", -1))], bytes(pos_data))

    # VerB 0: Attributes (stride 40, dxgi 10)
    norm16 = np.zeros((n, 4), dtype=np.float16)
    norm16[:, :3] = normals[:, :3]

    tan0_16 = np.zeros((n, 4), dtype=np.float16)
    tan0_16[:, :3] = tangents[:, :3]
    tan0_16[:, 3] = 1.0

    # Bitangent: normal x tangent
    bitan = np.cross(normals[:, :3], tangents[:, :3]) * bitan_sign
    tan1_16 = np.zeros((n, 4), dtype=np.float16)
    tan1_16[:, :3] = bitan
    tan1_16[:, 3] = 1.0

    if uv_xfs is None:
        uv_xfs = [uv_transform(uv0), uv_transform(uv1)]

    attr = np.zeros((n, 20), dtype=np.float16)
    attr[:, 0:4] = norm16
    attr[:, 12:16] = tan0_16
    attr[:, 16:20] = tan1_16
    # TEXCOORD0..3 are R16G16_UNORM: raw u16 (TEXCOORD2/3 stay 0 with identity transforms)
    bits = attr.view(np.uint16)
    bits[:, 4:6] = encode_uv(uv0, uv_xfs[0])
    bits[:, 6:8] = encode_uv(uv1, uv_xfs[1])

    attr_data = bytearray(struct.pack("<IIHHI", n, n * 40, 40, 7, 10))
    attr_data += attr.tobytes()
    b_attr = bundle.Blob(b"BreV", (1, 0), [(b"  dI", 0, struct.pack("<i", 0))], bytes(attr_data))

    return b_pos, b_attr


def make_indb_blob(indices: np.ndarray):
    """Creates IndB 0 (stride 4, dxgi 42)."""
    n = len(indices)
    ind_data = bytearray(struct.pack("<IIHHI", n, n * 4, 4, 1, 42))
    ind_data += indices.astype(np.uint32).tobytes()
    return bundle.Blob(b"BdnI", (1, 0), [(b"  dI", 0, struct.pack("<i", 0))], bytes(ind_data))


def make_mesh_blob(name: str, mat_idx: int, start_idx: int, idx_count: int, bbox: np.ndarray, is_shadow: bool = False, unique_verts: int = 0, uv_xfs=()):
    """Creates a Mesh v1.7 blob."""
    tri_count = idx_count // 3
    radius = float(np.linalg.norm((bbox[3:6] - bbox[0:3]) / 2.0))
    scale = max(radius, 1.0)
    if unique_verts == 0:
        unique_verts = idx_count

    m_data = bytearray()
    if is_shadow:
        # Shadow mesh header flags: (-1, 1, 3, 0, 255, 9, 0, 0, 0, 0, 1, 4)
        m_data += struct.pack("<hHHBBHB", -1, 1, 3, 0, 255, 9, 0)
    else:
        # Regular mesh header flags: (mat_idx, 1, 3, 0, 255, 17, 0, 0, 0, 0, 1, 4)
        m_data += struct.pack("<hHHBBHB", mat_idx, 1, 3, 0, 255, 17, 0)

    # Mesh 1.2 bytes (+0x12B, +0x12C in FH2's mesh object); the second is the morph flag: Model_LoadFromBundle opens the
    # Mrph blob without a check when any mesh sets it -> 1 here (no Mrph written) crashed the Autoshow at game+0x13e7398
    m_data += struct.pack("<BB", 0, 0)
    m_data += struct.pack("<B", 0)       # Mesh 1.3 bool (+0x12D): FH2 sets it only together with morphs
    m_data += struct.pack("<BH", 1, 4)   # b3=1, u4=4 (D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST)
    m_data += struct.pack("<iIiiII", 0, 0, start_idx, 0, idx_count, tri_count) # u6 = tri_count
    m_data += struct.pack("<fI", scale, unique_verts) # scale factor, u7 = unique_verts
    layout_id = 1 if is_shadow else 0
    m_data += struct.pack("<I", layout_id) # layout index

    if is_shadow:
        m_data += struct.pack("<I", 1)
        m_data += struct.pack("<iIII", -1, 0, 12, 0)
    else:
        m_data += struct.pack("<I", 2)
        m_data += struct.pack("<iIII", -1, 0, 12, 0)
        m_data += struct.pack("<iIII", 0, 1, 40, 0)

    m_data += struct.pack("<ii", 0, -1)  # v1=0, v2=-1
    m_data += struct.pack("<I", 0)       # n3=0
    m_data += struct.pack("<I", 0)       # v3=0

    if is_shadow:
        m_data += bytes(80)              # FH2's shadow meshes have all-zero UV transforms
    else:
        m_data += uv_tail(uv_xfs)

    b_meta = [
        (b"emaN", 0, name.encode("latin1")),
        (b"xoBB", 0, bbox.astype(np.float32).tobytes()),
    ]
    return bundle.Blob(b"hseM", (1, 7), b_meta, bytes(m_data))


def make_modl_blob(n_meshes: int, bbox: np.ndarray):
    """Creates a Modl v1.1 blob."""
    data = struct.pack("<HHHH", n_meshes, 1, 1, 1) + bytes.fromhex("0105ff007f00")
    b_meta = [
        (b"xoBB", 0, bbox.astype(np.float32).tobytes()),
    ]
    return bundle.Blob(b"ldoM", (1, 1), b_meta, data)


def convert_part_to_modelbin(part: carbin.FH1Part, donor_skel: Optional[bundle.Blob] = None, lod_name: str = "LODS0") -> bytes:
    """Converts a single FH1Part into full FH2 .modelbin bytes."""
    n_verts = part.vertex_count
    if n_verts == 0:
        raise ValueError(f"Part {part.name} has 0 vertices")

    part = to_fh2_axes(part)
    all_indices = []
    sub_mesh_infos = []

    for mesh in part.meshes:
        if mesh.triangle_count == 0:
            continue
        flat_idx = mesh.triangles.flatten()
        start_i = len(all_indices)
        cnt_i = len(flat_idx)
        all_indices.extend(flat_idx)
        fh2_mat = map_material(mesh.shader)
        sub_mesh_infos.append((mesh.shader, fh2_mat, start_i, cnt_i))

    if not all_indices:
        raise ValueError(f"Part {part.name} has no valid triangles")

    all_indices = np.array(all_indices, dtype=np.uint32)

    # Compute BBox
    b_min = np.min(part.positions, axis=0)
    b_max = np.max(part.positions, axis=0)
    bbox = np.concatenate([b_min, b_max])

    blobs = []
    if donor_skel:
        blobs.append(donor_skel)

    # MatI blobs
    mat_to_id = {}
    for _, fh2_mat, _, _ in sub_mesh_infos:
        if fh2_mat not in mat_to_id:
            mat_id = len(mat_to_id)
            mat_to_id[fh2_mat] = mat_id
            blobs.append(make_mati_blob(mat_id, fh2_mat))

    # Mesh blobs (all share one vertex buffer, so one UV transform per channel)
    uv_xfs = [uv_transform(part.uv0), uv_transform(part.uv1)]
    for _, fh2_mat, start_i, cnt_i in sub_mesh_infos:
        mat_id = mat_to_id[fh2_mat]
        m_name = f"{part.name}_{lod_name}"
        sub_idx = all_indices[start_i:start_i + cnt_i]
        u_verts = len(np.unique(sub_idx))
        blobs.append(make_mesh_blob(m_name, mat_id, start_i, cnt_i, bbox, is_shadow=False, unique_verts=u_verts, uv_xfs=uv_xfs))

    # Shadow mesh blob
    blobs.append(make_mesh_blob("Shadow", -1, 0, len(all_indices), bbox, is_shadow=True, unique_verts=n_verts))

    # IndB blob
    blobs.append(make_indb_blob(all_indices))

    # VLay blobs
    v_main, v_sh = make_vlay_blobs()
    blobs.append(v_main)
    blobs.append(v_sh)

    # VerB blobs
    b_pos, b_attr = make_verb_blobs(part.positions, part.normals, part.tangents, part.uv0, part.uv1, uv_xfs, bitan_sign=-1.0)
    blobs.append(b_pos)
    blobs.append(b_attr)

    # Modl blob
    n_meshes = len(sub_mesh_infos) + 1
    blobs.append(make_modl_blob(n_meshes, bbox))
    # Modl's u16 counts must match the blobs (meshes, VerB+IndB+MBuf+ConB+Skin, VLay, MatI); FH2 sizes its arrays by
    # them - the hard-coded 1/1/1 crashed FH2 at game+0xfd841f when the car loaded in the Autoshow
    vlayfix.update_modl_counts(blobs)

    return bundle.serialize(blobs)
