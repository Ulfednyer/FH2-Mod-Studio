"""
Forza Horizon 1 / Forza Motorsport 4 geometry (.carbin) reader.

Reverses the Xbox 360 big-endian .carbin formats (v5 for whole-car LOD models,
v1 for calipers/rotors):
  - Part extraction (22 car parts in LOD0: body, bumpers, wings, skirts, glass, lights...)
  - Part bounding boxes (origin 3f, min 3f, max 3f)
  - Per-mesh shader slots and index buffers (triangle strips with restart markers 0xFFFF / 0x00FFFFFF)
  - 28-byte vertex buffers (tag 3, stride 28, flag 1):
      bytes  0..6:  Position X, Y, Z (SHORT3N)
      bytes  6..8:  Position W (SHORT1N magnitude)
      bytes  8..12: UV0 (USHORT2N texture atlas UV, scaled & offset per subsection)
      bytes 12..16: UV1 (USHORT2N AO / livery mask UV, scaled & offset per subsection)
      bytes 16..24: QTangent / Frame (SHORT4N unit quaternion -> unit Normal & Tangent)
      bytes 24..28: Ambient occlusion / directional light (4x SNORM8)
"""

import os
import re
import struct
import sys
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

# Path to fh3port rendering tools if available
_FH3PORT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "fh3port"))
if _FH3PORT not in sys.path:
    sys.path.insert(0, _FH3PORT)


def decode_strips(idx: Union[List[int], Tuple[int, ...], np.ndarray], restart: int = 0xFFFF) -> np.ndarray:
    """Decodes triangle strip indices with restart markers into an (N, 3) triangle array."""
    tris = []
    run = []
    for i in idx:
        if i == restart or i < 0 or (restart != 0xFFFF and i >= 0xFFFFFF):
            run = []
            continue
        run.append(i)
        if len(run) >= 3:
            a, b, c = run[-3:]
            if a != b and b != c and a != c:
                tris.append((a, b, c) if len(run) % 2 else (b, a, c))
    if not tris:
        return np.zeros((0, 3), dtype=np.uint32)
    return np.array(tris, dtype=np.uint32)


def quat_to_matrix(q: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Converts unit quaternions (N, 4) in (x, y, z, w) order into UnitX (Normal),
    UnitY (Tangent), and UnitZ (Bitangent) matrices matching Forza / XNA coordinate system:
        Normal    = Matrix.FirstRow  (UnitX image)
        Tangent   = Matrix.SecondRow (UnitY image)
        Bitangent = Matrix.ThirdRow  (UnitZ image)
    """
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]

    # UnitX image (Normal in Forza):
    nx = 1.0 - 2.0 * (y * y + z * z)
    ny = 2.0 * (x * y + z * w)
    nz = 2.0 * (x * z - y * w)
    normals = np.column_stack([nx, ny, nz])
    n_len = np.linalg.norm(normals, axis=1, keepdims=True)
    n_len = np.where(n_len < 1e-9, 1.0, n_len)
    normals = normals / n_len

    # UnitY image (Tangent):
    tx = 2.0 * (x * y - z * w)
    ty = 1.0 - 2.0 * (x * x + z * z)
    tz = 2.0 * (y * z + x * w)
    tangents = np.column_stack([tx, ty, tz])
    t_len = np.linalg.norm(tangents, axis=1, keepdims=True)
    t_len = np.where(t_len < 1e-9, 1.0, t_len)
    tangents = tangents / t_len

    # UnitZ image (Bitangent):
    bx = 2.0 * (x * z + y * w)
    by = 2.0 * (y * z - x * w)
    bz = 1.0 - 2.0 * (x * x + y * y)
    bitangents = np.column_stack([bx, by, bz])
    b_len = np.linalg.norm(bitangents, axis=1, keepdims=True)
    b_len = np.where(b_len < 1e-9, 1.0, b_len)
    bitangents = bitangents / b_len

    return normals, tangents, bitangents


class FH1Mesh:
    """A sub-mesh within a part sharing a specific shader slot and index buffer."""

    def __init__(self, shader: str, triangles: np.ndarray, raw_indices: np.ndarray, index_size: int):
        self.shader: str = shader
        self.triangles: np.ndarray = triangles  # (N, 3) uint32
        self.raw_indices: np.ndarray = raw_indices  # raw strip indices
        self.index_size: int = index_size  # 2 or 4 bytes

    @property
    def triangle_count(self) -> int:
        return len(self.triangles)

    def __repr__(self) -> str:
        return f"<FH1Mesh shader='{self.shader}' tris={self.triangle_count}>"


class FH1Part:
    """A named component (e.g. body, bumperFa, winga, caliperLF) with bounds and vertex buffer."""

    def __init__(self, name: str, origin: np.ndarray, min_box: np.ndarray, max_box: np.ndarray):
        self.name: str = name
        self.origin: np.ndarray = origin
        self.min_box: np.ndarray = min_box
        self.max_box: np.ndarray = max_box
        self.center: np.ndarray = origin + (min_box + max_box) / 2.0
        self.extent: np.ndarray = (max_box - min_box) / 2.0
        self.meshes: List[FH1Mesh] = []

        # Vertex buffers
        self.positions: np.ndarray = np.zeros((0, 3), dtype=np.float32)
        self.uv0: np.ndarray = np.zeros((0, 2), dtype=np.float32)
        self.uv1: np.ndarray = np.zeros((0, 2), dtype=np.float32)
        self.colors: np.ndarray = np.zeros((0, 4), dtype=np.uint8)
        self.normals: np.ndarray = np.zeros((0, 3), dtype=np.float32)
        self.tangents: np.ndarray = np.zeros((0, 3), dtype=np.float32)
        self.bitangents: np.ndarray = np.zeros((0, 3), dtype=np.float32)
        self.quaternions: np.ndarray = np.zeros((0, 4), dtype=np.float32)

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def triangle_count(self) -> int:
        return sum(m.triangle_count for m in self.meshes)

    def __repr__(self) -> str:
        return f"<FH1Part '{self.name}' verts={self.vertex_count} tris={self.triangle_count} meshes={len(self.meshes)}>"


class FH1Carbin:
    """Parses and manages an FH1 / FM4 .carbin file."""

    def __init__(self, version: int = 5):
        self.version: int = version
        self.parts: Dict[str, FH1Part] = {}

    @classmethod
    def load(cls, path_or_bytes: Union[str, bytes]) -> "FH1Carbin":
        """Loads and parses an FH1 .carbin file from path or raw bytes."""
        if isinstance(path_or_bytes, (str, bytes, os.PathLike)) and not isinstance(path_or_bytes, bytes):
            with open(path_or_bytes, "rb") as f:
                data = f.read()
        else:
            data = path_or_bytes

        if len(data) < 16:
            raise ValueError(f"Carbin data too small: {len(data)} bytes")

        ver = struct.unpack_from(">I", data, 0)[0]
        model = cls(version=ver)
        model._parse(data)
        return model

    def _parse(self, data: bytes) -> None:
        p = 0
        file_type = struct.unpack_from(">I", data, 0)[0]
        p = 4

        # Wheels (type 3) and calipers/rotors (type 1)
        if file_type == 1 or file_type == 3:
            head_length = 4 + (920 if file_type == 3 else 0x354)
            p = head_length
        elif file_type == 5 or file_type == 2:
            if file_type == 5:
                p += 0x150
                extra = struct.unpack_from(">I", data, p)[0]
                p += 4 + extra * 0x20 + 12
            else:
                p += 0x15c
            records = struct.unpack_from(">I", data, p)[0]
            p += 4 + (records * 140) + 0x344
        else:
            raise ValueError(f"Unsupported .carbin type {file_type}")

        # Draw lists
        lists = struct.unpack_from(">I", data, p)[0] * 2
        p += 4
        for _ in range(lists):
            l_len = struct.unpack_from(">I", data, p)[0]
            p += 4 + l_len * 4

        # Before sections marker (4 bytes)
        p += 4
        sec_count = struct.unpack_from(">I", data, p)[0]
        p += 4

        for _ in range(sec_count):
            marker = struct.unpack_from(">I", data, p)[0]
            if marker in (0x2c9, 2, 5):
                p += 4

            bounds = struct.unpack_from(">9f", data, p)
            p += 36

            # Unk1c (28 bytes)
            p += 0x1c

            # ACount (16 bytes per entry) + AfterA (4 bytes)
            a_count = struct.unpack_from(">I", data, p)[0]
            p += 4 + a_count * 16 + 4

            # BCount (2 bytes per entry) + Pre (4 bytes) + VbTest (8 bytes)
            b_count = struct.unpack_from(">I", data, p)[0]
            p += 4 + b_count * 2 + 4 + 8

            # Part name
            nlen = data[p]
            p += 1
            sec_name = data[p:p + nlen].decode("ascii", errors="ignore")
            p += nlen + 4  # post_name (4 bytes)

            # Lod vertex buffer
            v_count, v_stride = struct.unpack_from(">II", data, p)
            p += 8
            flag = struct.unpack_from(">I", data, p)[0]
            p += (8 if flag != 0 else 4) + (v_count * v_stride) + 4  # after_lod (4 bytes)

            # Subsections
            subs = struct.unpack_from(">I", data, p)[0]
            p += 4
            subsections = []
            for _ in range(subs):
                p += 5  # pre5
                sub_uv = struct.unpack_from(">8f", data, p)
                p += 32
                p += 36  # fixed36
                sub_nlen = struct.unpack_from(">I", data, p)[0]
                p += 4
                sub_name = data[p:p + sub_nlen].decode("ascii", errors="ignore")
                p += sub_nlen + 8 + 56 + 4  # lod(4), idxtype(4), fixed56, three(4)
                sub_idx_word = struct.unpack_from(">I", data, p)[0]
                p += 4
                stripped = (sub_idx_word == 2)
                indices = []
                idx_size = 2
                if stripped:
                    p += 8
                else:
                    idx_count, idx_size = struct.unpack_from(">II", data, p)
                    p += 8
                    if idx_size == 2:
                        indices = list(struct.unpack_from(f">{idx_count}H", data, p))
                    else:
                        indices = list(struct.unpack_from(f">{idx_count}I", data, p))
                    p += idx_count * idx_size
                p += 4  # sub_tail (4 bytes)
                subsections.append((sub_name, sub_uv, indices, idx_size))

            p += 4  # after_subs (4 bytes)

            # Lod0 vertex buffer
            v0_count, v0_stride = struct.unpack_from(">II", data, p)
            p += 8
            flag0 = struct.unpack_from(">I", data, p)[0]
            extra0_len = 8 if flag0 != 0 else 4
            p += extra0_len
            lod0_data = data[p:p + v0_count * v0_stride]
            p += v0_count * v0_stride

            # Damage tables
            p += 9  # post9
            d_count, d_stride = struct.unpack_from(">II", data, p)
            p += 8
            d_flag = struct.unpack_from(">I", data, p)[0]
            p += (8 if d_flag != 0 else 4) + d_count * d_stride + 4  # mid (4 bytes)

            d0_count, d0_stride = struct.unpack_from(">II", data, p)
            p += 8
            d0_flag = struct.unpack_from(">I", data, p)[0]
            p += (8 if d0_flag != 0 else 4) + d0_count * d0_stride

            # Build FH1Part: prefer Lod0, fallback to Lod
            vert_count = v0_count if v0_count > 0 else v_count
            vb_data = lod0_data
            if vert_count == 0 or len(vb_data) == 0:
                continue

            origin = np.array(bounds[:3], dtype=np.float32)
            min_b = np.array(bounds[3:6], dtype=np.float32)
            max_b = np.array(bounds[6:9], dtype=np.float32)
            part = FH1Part(sec_name, origin, min_b, max_b)

            # Decode Positions
            half = (max_b - min_b) / 2.0
            scale = float(np.sqrt(np.sum(half * half)))
            center = origin + (min_b + max_b) / 2.0

            pos = np.zeros((vert_count, 3), dtype=np.float32)
            raw_v = np.frombuffer(vb_data, dtype=np.uint8).reshape(vert_count, 28)
            s_xyz = raw_v[:, 0:6].copy().view(">i2").reshape(vert_count, 3).astype(np.float32) / 32767.0
            w = raw_v[:, 6:8].copy().view(">i2").flatten().astype(np.float32) / 32767.0
            pos = center + s_xyz * w[:, None] * scale
            part.positions = pos.astype(np.float32)

            # Decode Quaternions, Normals, Tangents, Bitangents
            q_s16 = raw_v[:, 16:24].copy().view(">i2").reshape(vert_count, 4).astype(np.float32) / 32767.0
            q_norm = np.linalg.norm(q_s16, axis=1, keepdims=True)
            q_norm = np.where(q_norm < 1e-9, 1.0, q_norm)
            q = q_s16 / q_norm
            part.quaternions = q
            part.normals, part.tangents, part.bitangents = quat_to_matrix(q)

            # Colors / Ambient light (offset 24..28)
            part.colors = raw_v[:, 24:28].copy()

            # UVs using the primary subsection transform
            if subsections:
                sub0_uv = subsections[0][1]
                u0_raw = raw_v[:, 8:10].copy().view(">u2").flatten().astype(np.float32) / 65535.0
                v0_raw = raw_v[:, 10:12].copy().view(">u2").flatten().astype(np.float32) / 65535.0
                part.uv0 = np.column_stack([u0_raw * sub0_uv[1] + sub0_uv[0], v0_raw * sub0_uv[3] + sub0_uv[2]])

                u1_raw = raw_v[:, 12:14].copy().view(">u2").flatten().astype(np.float32) / 65535.0
                v1_raw = raw_v[:, 14:16].copy().view(">u2").flatten().astype(np.float32) / 65535.0
                part.uv1 = np.column_stack([u1_raw * sub0_uv[5] + sub0_uv[4], v1_raw * sub0_uv[7] + sub0_uv[6]])
            else:
                part.uv0 = np.zeros((vert_count, 2), dtype=np.float32)
                part.uv1 = np.zeros((vert_count, 2), dtype=np.float32)

            # Subsections / Meshes
            for sname, suv, idxs, isz in subsections:
                if not idxs:
                    continue
                rs = 0xFFFF if isz == 2 else 0x00FFFFFF
                tris = decode_strips(idxs, rs)
                if len(tris) > 0:
                    part.meshes.append(FH1Mesh(sname, tris, np.array(idxs, dtype=np.uint32), isz))

            self.parts[sec_name] = part

    def export_obj(self, out_path: str, parts: Optional[List[str]] = None) -> None:
        """Exports the geometry as a standard Wavefront .obj file with groups and materials."""
        selected_parts = [self.parts[p] for p in (parts or self.parts.keys()) if p in self.parts]
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# Exported from FH1/FM4 .carbin by fh2mod\n")
            f.write(f"# Parts: {len(selected_parts)}\n\n")

            vert_offset = 1  # OBJ 1-based indexing

            for part in selected_parts:
                f.write(f"g {part.name}\n")

                # Positions
                for x, y, z in part.positions:
                    f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")

                # Texture coordinates
                for u, v in part.uv0:
                    f.write(f"vt {u:.6f} {1.0 - v:.6f}\n")

                # Normals
                for nx, ny, nz in part.normals:
                    f.write(f"vn {nx:.6f} {ny:.6f} {nz:.6f}\n")

                # Meshes
                for mesh in part.meshes:
                    f.write(f"usemtl {mesh.shader}\n")
                    for a, b, c in mesh.triangles:
                        ia, ib, ic = a + vert_offset, b + vert_offset, c + vert_offset
                        f.write(f"f {ia}/{ia}/{ia} {ib}/{ib}/{ib} {ic}/{ic}/{ic}\n")

                vert_offset += part.vertex_count

    def render_png(self, out_path: str, view: str = "side", parts: Optional[List[str]] = None, size: int = 1024) -> None:
        """Renders shaded views of the car using render.py."""
        import render

        selected_parts = [self.parts[p] for p in (parts or self.parts.keys()) if p in self.parts]
        triangles = []
        mesh_ids = []

        for p_idx, part in enumerate(selected_parts):
            for mesh in part.meshes:
                if len(mesh.triangles) > 0:
                    triangles.append(part.positions[mesh.triangles])
                    mesh_ids += [p_idx] * len(mesh.triangles)

        if not triangles:
            raise ValueError("No triangles to render")

        T = np.concatenate(triangles, axis=0)
        M = np.array(mesh_ids, dtype=np.int32)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        img = render.render(T, M, view, size)
        render.png(out_path, img)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python carbin.py <file.carbin> [out.obj | out.png [side|front|top]]")
        sys.exit(1)

    carbin_file = sys.argv[1]
    car = FH1Carbin.load(carbin_file)
    print(f"Loaded {os.path.basename(carbin_file)}: version {car.version}, {len(car.parts)} parts")
    total_tris = sum(p.triangle_count for p in car.parts.values())
    total_verts = sum(p.vertex_count for p in car.parts.values())
    print(f"Total: {total_verts:,} vertices, {total_tris:,} triangles across {len(car.parts)} parts:")
    for name, p in car.parts.items():
        shaders = ", ".join(m.shader for m in p.meshes) or "none"
        print(f"  {name:<16}: {p.vertex_count:6,d} verts, {p.triangle_count:6,d} tris [{shaders}]")

    if len(sys.argv) >= 3:
        out = sys.argv[2]
        if out.endswith(".obj"):
            car.export_obj(out)
            print(f"Exported OBJ to {out}")
        elif out.endswith(".png"):
            view = sys.argv[3] if len(sys.argv) > 3 else "side"
            # Omit race parts on default stock render
            stock_parts = [p for p in car.parts.keys() if not p.endswith("race")]
            car.render_png(out, view=view, parts=stock_parts)
            print(f"Rendered {view} view to {out}")
