from __future__ import annotations

from dataclasses import dataclass

from spritespatial.colour_field import RGBA, is_blackish


@dataclass(frozen=True)
class MeshBuildConfig:
    voxel_size: float = 0.05
    model_depth_units: float = 0.60
    simplify_mesh: bool = True
    cleanup_mode: str = "merged_faces"


FACE_DELTAS = {
    "back": (0, 0, -1),
    "front": (0, 0, 1),
    "left": (-1, 0, 0),
    "right": (1, 0, 0),
    "up": (0, -1, 0),
    "down": (0, 1, 0),
}


def build_surface_mesh(
    volume: list[list[list[bool]]],
    colour_field: list[list[list[RGBA]]],
    config: MeshBuildConfig,
) -> tuple[dict[str, list], dict]:
    depth = len(volume)
    height = len(volume[0])
    width = len(volume[0][0])
    voxel_x = config.voxel_size
    voxel_y = config.voxel_size
    voxel_z = config.model_depth_units / max(depth, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -config.model_depth_units * 0.5

    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    exposed_faces = 0
    black_side_faces = 0
    internal_faces_removed = 0
    colour_set: set[RGBA] = set()

    def occupied(x: int, y: int, z: int) -> bool:
        if x < 0 or y < 0 or z < 0 or x >= width or y >= height or z >= depth:
            return False
        return volume[z][y][x]

    for z in range(depth):
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        for y in range(height):
            y0 = total_height - (y + 1) * voxel_y
            y1 = total_height - y * voxel_y
            for x in range(width):
                if not volume[z][y][x]:
                    continue
                x0 = x * voxel_x - total_width * 0.5
                x1 = x0 + voxel_x
                for face, delta in FACE_DELTAS.items():
                    nx, ny, nz = x + delta[0], y + delta[1], z + delta[2]
                    if occupied(nx, ny, nz):
                        internal_faces_removed += 1
                        continue
                    exposed_faces += 1
                    colour = _face_colour(colour_field, x, y, z, face)
                    colour_set.add(colour)
                    if face not in {"front", "back"} and _is_outline_like(colour):
                        black_side_faces += 1
                    _add_face(vertices, normals, colors, indices, face, x0, x1, y0, y1, z0, z1, colour)

    mesh = {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
    }
    report = {
        "vertex_count": len(vertices),
        "triangle_count": len(indices) // 3,
        "exposed_face_count": exposed_faces,
        "internal_faces_removed": internal_faces_removed,
        "black_side_face_count": black_side_faces,
        "black_side_face_percentage": black_side_faces / exposed_faces if exposed_faces else 0.0,
        "material_colour_count": len(colour_set),
        "bounding_box_dimensions": [total_width, total_height, config.model_depth_units],
    }
    return mesh, report


def _face_colour(
    colour_field: list[list[list[RGBA]]],
    x: int,
    y: int,
    z: int,
    face: str,
) -> RGBA:
    colour = colour_field[z][y][x]
    if face in {"front", "back"} or not _is_outline_like(colour):
        return colour

    # Side/top/bottom faces should inherit body-region colour, not become a
    # black slab just because the exposed voxel sits on a sprite outline.
    depth = len(colour_field)
    height = len(colour_field[0])
    width = len(colour_field[0][0])
    best: tuple[int, RGBA] | None = None
    for radius in range(1, 5):
        for dz in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    distance = abs(dx) + abs(dy) + abs(dz)
                    if distance == 0 or distance > radius:
                        continue
                    nx = x + dx
                    ny = y + dy
                    nz = z + dz
                    if nx < 0 or ny < 0 or nz < 0 or nx >= width or ny >= height or nz >= depth:
                        continue
                    candidate = colour_field[nz][ny][nx]
                    if candidate[3] == 0 or _is_outline_like(candidate):
                        continue
                    if best is None or distance < best[0]:
                        best = (distance, candidate)
        if best is not None:
            return best[1]
    return colour


def _is_outline_like(colour: RGBA) -> bool:
    return colour[3] > 0 and max(colour[0], colour[1], colour[2]) <= 72


def _add_face(
    vertices: list[list[float]],
    normals: list[list[float]],
    colors: list[list[float]],
    indices: list[int],
    face: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    colour: RGBA,
) -> None:
    if face == "back":
        verts = ([x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0])
        normal = [0, 0, -1]
    elif face == "front":
        verts = ([x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1])
        normal = [0, 0, 1]
    elif face == "left":
        verts = ([x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0])
        normal = [-1, 0, 0]
    elif face == "right":
        verts = ([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])
        normal = [1, 0, 0]
    elif face == "up":
        verts = ([x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1])
        normal = [0, 1, 0]
    else:
        verts = ([x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0])
        normal = [0, -1, 0]

    start = len(vertices)
    rgba = [colour[0] / 255.0, colour[1] / 255.0, colour[2] / 255.0, colour[3] / 255.0]
    vertices.extend([list(vertex) for vertex in verts])
    normals.extend([normal, normal, normal, normal])
    colors.extend([rgba, rgba, rgba, rgba])
    indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])
