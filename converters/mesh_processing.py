"""Mesh processing utilities for converting Roblox mesh formats."""

import logging
import struct

logger = logging.getLogger(__name__)


def is_mesh_data(data: bytes) -> bool:
    """Check if bytes represent a Roblox mesh file."""
    if not data:
        return False
    return data.startswith(b'version ') or data[:4] in (b'\x00\x01\x00\x00',)


def convert(data: bytes) -> str | None:
    """Convert Roblox mesh binary to OBJ format string."""
    try:
        if data.startswith(b'version '):
            return _convert_text_mesh(data)
        return _convert_binary_mesh(data)
    except Exception as exc:
        logger.error('Mesh conversion failed: %s', exc)
        return None


def _convert_text_mesh(data: bytes) -> str | None:
    """Convert text-format Roblox mesh to OBJ."""
    try:
        text = data.decode('utf-8', errors='replace')
    except Exception:
        return None

    lines = text.splitlines()
    vertices = []
    faces = []
    parsing_verts = False
    parsing_faces = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('version ') or line.startswith('numfaces '):
            continue
        if line.startswith('{'):
            parsing_verts = True
            parsing_faces = False
            continue
        if line.startswith('}'):
            continue

        if parsing_verts and ',' in line:
            try:
                parts = line.strip(', ').split(',')
                if len(parts) >= 3:
                    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    vertices.append((x, y, z))
            except ValueError:
                parsing_verts = False
                parsing_faces = True
                continue

        if parsing_faces:
            try:
                nums = [int(n) for n in line.strip(', ').split(',') if n.strip()]
                if len(nums) >= 3:
                    faces.append([n + 1 for n in nums])
            except ValueError:
                continue

    return _build_obj(vertices, faces)


def _convert_binary_mesh(data: bytes) -> str | None:
    """Convert binary-format Roblox mesh to OBJ."""
    if len(data) < 16 or data[:4] != b'\x00\x01\x00\x00':
        return None

    pos = 4
    vert_count = struct.unpack_from('<I', data, pos)[0]
    pos += 4

    vertices = []
    for _ in range(min(vert_count, 100000)):
        if pos + 12 > len(data):
            break
        x = struct.unpack_from('<f', data, pos)[0]
        y = struct.unpack_from('<f', data, pos + 4)[0]
        z = struct.unpack_from('<f', data, pos + 8)[0]
        vertices.append((x, y, z))
        pos += 12

    faces = []
    if pos + 4 <= len(data):
        face_count = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        for _ in range(min(face_count, 100000)):
            if pos + 12 > len(data):
                break
            i1 = struct.unpack_from('<I', data, pos)[0] + 1
            i2 = struct.unpack_from('<I', data, pos + 4)[0] + 1
            i3 = struct.unpack_from('<I', data, pos + 8)[0] + 1
            faces.append((i1, i2, i3))
            pos += 12

    return _build_obj(vertices, faces)


def _build_obj(vertices: list, faces: list) -> str:
    """Build OBJ string from vertex and face data."""
    lines = ['# Converted by RobloxCacheScraper']
    lines.append(f'# {len(vertices)} vertices, {len(faces)} faces')
    lines.append('')

    for v in vertices:
        lines.append(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}')

    lines.append('')
    for f in faces:
        if len(f) == 3:
            lines.append(f'f {f[0]} {f[1]} {f[2]}')
        elif len(f) >= 4:
            lines.append(f'f {f[0]} {f[1]} {f[2]}')

    return '\n'.join(lines)
