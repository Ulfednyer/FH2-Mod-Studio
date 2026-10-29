"""
Forza Horizon 1 / Forza Motorsport 4 geometry (.carbin) reader.

Reverses the Xbox 360 big-endian .carbin formats (v5 for whole-car LOD models,
v1 for calipers/rotors):
  - Part extraction (22 car parts in LOD0: body, bumpers, wings, skirts, glass, lights...)
  - Part bounding boxes (center + half-extent box floats, tag 5)
  - Per-mesh shader slots and index buffers (triangle strips with restart markers 0xFFFF / 0x00FFFFFF)
  - 28-byte vertex buffers (tag 3, stride 28, flag 1):
      bytes  0..4:  UV0 (texture atlas UV, USHORT2N normalized to [0, 1])
      bytes  4..8:  UV1 (AO / livery mask UV, USHORT2N normalized to [0, 1])
      bytes  8..16: Position (SHORT4N, x = center + q[:3] * extent)
      bytes 16..20: Color / AO tint (D3DCOLOR, 4x uint8)
      bytes 20..28: QTangent (SHORT4N unit quaternion -> unit Normal & Tangent)
"""

import os
import re
import struct
import sys
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

# Path to fh3port rendering tools if available
_FH3PORT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "fh3port"))
if _FH3PORT not in sys.path:
    sys.path.insert(0, _FH3PORT)


def decode_strips(idx: Union[List[int], Tuple[int, ...], np.ndarray], restart: int) -> np.ndarray:
    """Decodes triangle strip indices with restart markers into an (N, 3) triangle array."""
    tris = []
    run = []
    for i in idx:
        if i == restart:
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


def qtangent_to_vectors(q: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Converts unit quaternions (N, 4) in (x, y, z, w) order into unit Normals (N, 3)
    and unit Tangents (N, 3) using standard quaternion rotation:
        Normal  = Q * (0, 0, 1) * Q^-1
        Tangent = Q * (1, 0, 0) * Q^-1
    """
    qx, qy, qz, qw = q[:, 0], q[:, 1], q[:, 2], q[:, 3]

    # Normal: rotated (0, 0, 1)
    nx = 2.0 * (qx * qz + qy * qw)
    ny = 2.0 * (qy * qz - qx * qw)
    nz = 1.0 - 2.0 * (qx * qx + qy * qy)
    normals = np.column_stack([nx, ny, nz])
    n_len = np.linalg.norm(normals, axis=1, keepdims=True)
    n_len = np.where(n_len < 1e-9, 1.0, n_len)
    normals = normals / n_len

    # Tangent: rotated (1, 0, 0)
    tx = 1.0 - 2.0 * (qy * qy + qz * qz)
    ty = 2.0 * (qx * qy + qz * qw)
    tz = 2.0 * (qx * qz - qy * qw)
    tangents = np.column_stack([tx, ty, tz])
    t_len = np.linalg.norm(tangents, axis=1, keepdims=True)
    t_len = np.where(t_len < 1e-9, 1.0, t_len)
    tangents = tangents / t_len

    return normals, tangents


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

    def __init__(self, name: str, center: np.ndarray, extent: np.ndarray):
        self.name: str = name
        self.center: np.ndarray = center  # (3,) in world coordinates (m)
        self.extent: np.ndarray = extent  # (3,) half extents (m)
        self.min_box: np.ndarray = center - extent
        self.max_box: np.ndarray = center + extent
        self.meshes: List[FH1Mesh] = []

        # Vertex buffers (stride 28)
        self.positions: np.ndarray = np.zeros((0, 3), dtype=np.float32)
        self.uv0: np.ndarray = np.zeros((0, 2), dtype=np.float32)
        self.uv1: np.ndarray = np.zeros((0, 2), dtype=np.float32)
        self.colors: np.ndarray = np.zeros((0, 4), dtype=np.uint8)
        self.normals: np.ndarray = np.zeros((0, 3), dtype=np.float32)
        self.tangents: np.ndarray = np.zeros((0, 3), dtype=np.float32)
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
        n = len(data)

        # Find all named parts. In FH1 carbins, parts are marked with:
        # \x01\x00\x00\x00 [len: 1 byte in BE dword] [name] \x00
        part_matches = list(re.finditer(rb"\x01\x00\x00\x00([\x03-\x30])([a-zA-Z0-9_]{3,40})\x00", data))
        if not part_matches:
            # Fallback: single-part component (e.g. caliperLF)
            # Find any ASCII identifier in header
            part_matches = list(re.finditer(rb"([\x03-\x30])([a-zA-Z0-9_]{3,40})\x00", data[:2048]))
            part_matches = [m for m in part_matches if m.group(2).decode("latin1", errors="ignore") in ("caliperLF", "rotorLF")]

        for idx, m in enumerate(part_matches):
            pname = m.group(2).decode("ascii", errors="ignore")
            poff = m.start()
            next_poff = part_matches[idx + 1].start() if idx + 1 < len(part_matches) else n

            # 1. Bounding box record sits right before the part name
            # Tag 5 (u32), center (3f), min (3f), max (3f), 1.0 (float) = 44 bytes
            box = None
            for o in range(poff - 44, max(0, poff - 300), -1):
                if data[o:o + 4] == b"\x00\x00\x00\x05" and data[o + 40:o + 44] == b"\x3f\x80\x00\x00":
                    center = np.array(struct.unpack_from(">3f", data, o + 4), dtype=np.float32)
                    lo = np.array(struct.unpack_from(">3f", data, o + 16), dtype=np.float32)
                    hi = np.array(struct.unpack_from(">3f", data, o + 28), dtype=np.float32)
                    # Extent is the half-extent
                    extent = np.maximum(np.abs(hi), np.abs(lo))
                    box = (center, extent)
                    break

            if box is None:
                # Default box fallback if omitted
                box = (np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32))

            center, extent = box
            part = FH1Part(pname, center, extent)

            # 2. Find vertex buffer in this part:
            # Tag 3 (u32), count (u32), stride 28 (u32), flag 1 (u32)
            vb_hdr = None
            for o in range(poff, next_poff - 16):
                tag, count, stride, flag = struct.unpack_from(">IIII", data, o)
                if tag == 3 and stride == 28 and flag == 1 and 3 <= count <= 200000:
                    vb_hdr = (o, o + 16, count, stride)
                    break

            if vb_hdr is None:
                continue

            v_hdr_off, v_data_off, v_count, v_stride = vb_hdr

            # Unpack 28-byte vertex data
            raw_v = np.frombuffer(data[v_data_off:v_data_off + v_count * v_stride], np.uint8).reshape(v_count, v_stride)

            # UV0: offset 0..4 (2x USHORT2N)
            part.uv0 = raw_v[:, 0:4].copy().view(">u2").reshape(v_count, 2).astype(np.float32) / 65535.0

            # UV1: offset 4..8 (2x USHORT2N)
            part.uv1 = raw_v[:, 4:8].copy().view(">u2").reshape(v_count, 2).astype(np.float32) / 65535.0

            # Positions: offset 8..14 (3x SHORT4N normalized [-1.0, 1.0])
            q_pos = raw_v[:, 8:14].copy().view(">i2").reshape(v_count, 3).astype(np.float32) / 32767.0
            part.positions = (center + q_pos * extent).astype(np.float32)

            # Colors: offset 16..20 (4x uint8)
            part.colors = raw_v[:, 16:20].copy()

            # QTangent: offset 20..28 (4x SHORT4N unit quaternion)
            part.quaternions = raw_v[:, 20:28].copy().view(">i2").reshape(v_count, 4).astype(np.float32) / 32767.0
            part.normals, part.tangents = qtangent_to_vectors(part.quaternions)

            # 3. Find meshes and index buffers between part name and vertex buffer
            # Shaders appear as: slen (u32 BE) + string + \x00
            mesh_regions = []
            for o in range(poff + 8, v_hdr_off - 8):
                slen = struct.unpack_from(">I", data, o)[0]
                if 2 <= slen <= 40 and o + 4 + slen < v_hdr_off:
                    cand = data[o + 4:o + 4 + slen]
                    if cand.replace(b"_", b"").isalnum() and data[o + 4 + slen] == 0:
                        sname = cand.decode("ascii", errors="ignore")
                        mesh_regions.append((o, o + 4 + slen + 1, sname))

            for m_idx, (s_start, s_end, sname) in enumerate(mesh_regions):
                m_next = mesh_regions[m_idx + 1][0] if m_idx + 1 < len(mesh_regions) else v_hdr_off
                # Find index buffer header in range [s_end, m_next]
                for io in range(s_end, m_next - 8):
                    cnt, sz = struct.unpack_from(">II", data, io)
                    if sz in (2, 4) and 3 <= cnt <= 200000 and io + 8 + cnt * sz <= v_hdr_off:
                        # Validate restart marker in first block
                        chk_cnt = min(cnt, 32)
                        vals = struct.unpack_from(">%d%s" % (chk_cnt, "H" if sz == 2 else "I"), data, io + 8)
                        rs = 0xFFFF if sz == 2 else 0x00FFFFFF
                        if rs in vals:
                            raw_idx = struct.unpack_from(">%d%s" % (cnt, "H" if sz == 2 else "I"), data, io + 8)
                            tris = decode_strips(raw_idx, rs)
                            if len(tris) > 0 and tris.max() < v_count:
                                part.meshes.append(FH1Mesh(sname, tris, np.array(raw_idx, dtype=np.uint32), sz))
                            break

            self.parts[pname] = part

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
