from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


PRIMITIVE_TYPES = {
    "cuboid",
    "rounded_cuboid",
    "ellipsoid",
    "capsule",
    "tapered_prism",
    "shell",
    "rigid_slab",
}

ZFIELDS_BY_PART = {
    "head": ("ellipsoid", "ellipsoid", 0.82, 0.12, "semantic_blend", "soft_boundary"),
    "face": ("rounded_cuboid", "rounded", 0.58, 0.20, "semantic_blend", "soft_boundary"),
    "hair": ("ellipsoid", "ellipsoid", 0.72, 0.14, "semantic_blend", "soft_boundary"),
    "torso": ("rounded_cuboid", "rounded", 0.62, 0.0, "semantic_blend", "soft_boundary"),
    "left_arm": ("tapered_prism", "tapered", 0.52, 0.08, "limb_taper", "soft_boundary"),
    "right_arm": ("tapered_prism", "tapered", 0.52, 0.08, "limb_taper", "soft_boundary"),
    "left_leg": ("tapered_prism", "tapered", 0.56, -0.04, "limb_taper", "soft_boundary"),
    "right_leg": ("tapered_prism", "tapered", 0.56, -0.04, "limb_taper", "soft_boundary"),
    "left_foot": ("rounded_cuboid", "rounded_cuboid", 0.72, -0.02, "foot_rounding", "soft_boundary"),
    "right_foot": ("rounded_cuboid", "rounded_cuboid", 0.72, -0.02, "foot_rounding", "soft_boundary"),
    "outline": ("shell", "shell", 0.14, 0.42, "rim_only", "outline_shell"),
    "equipment": ("rigid_slab", "flat", 0.42, 0.02, "rigid", "hard_boundary"),
    "unknown": ("cuboid", "rounded", 0.38, 0.0, "fallback", "soft_boundary"),
}


@dataclass(frozen=True)
class PrimitiveAssignment:
    part_id: int
    name: str
    semantic_label: str
    primitive_type: str
    zfield_profile: str
    local_depth: float
    z_offset: float
    smoothing_policy: str
    boundary_policy: str
    fallback: bool
    pixel_count: int
    bbox: list[int]


def assign_primitives(parts: list[dict[str, Any]], profile: dict[str, Any] | None = None) -> list[PrimitiveAssignment]:
    assignments: list[PrimitiveAssignment] = []
    for part_id, part in enumerate(parts):
        name = str(part.get("name", "unknown"))
        semantic_label = str(part.get("semantic_label", name))
        primitive, zfield, depth, offset, smoothing, boundary = _mapping_for_part(name, semantic_label)
        fallback = name == "unknown" or primitive not in PRIMITIVE_TYPES
        if fallback:
            primitive = "cuboid"
            zfield = "rounded"
        if profile and profile.get("primitive_smoothing") == "semantic_constrained" and smoothing != "rim_only":
            smoothing = "semantic_constrained"
        assignments.append(
            PrimitiveAssignment(
                part_id=part_id,
                name=name,
                semantic_label=semantic_label,
                primitive_type=primitive,
                zfield_profile=zfield,
                local_depth=float(depth),
                z_offset=float(offset),
                smoothing_policy=smoothing,
                boundary_policy=boundary,
                fallback=fallback,
                pixel_count=len(part.get("pixels", [])),
                bbox=list(part.get("bbox", [0, 0, 0, 0])),
            )
        )
    return assignments


def primitive_count_by_type(assignments: list[PrimitiveAssignment]) -> dict[str, int]:
    return dict(Counter(item.primitive_type for item in assignments))


def assignments_to_json(assignments: list[PrimitiveAssignment]) -> list[dict[str, Any]]:
    return [asdict(item) for item in assignments]


def _mapping_for_part(name: str, semantic_label: str) -> tuple[str, str, float, float, str, str]:
    if name in ZFIELDS_BY_PART:
        return ZFIELDS_BY_PART[name]
    if semantic_label in {"boots/feet", "boots", "feet"}:
        return ("rounded_cuboid", "rounded_cuboid", 0.72, -0.02, "foot_rounding", "soft_boundary")
    if semantic_label == "equipment/shield/sword":
        return ZFIELDS_BY_PART["equipment"]
    if semantic_label == "hair/hat":
        return ZFIELDS_BY_PART["hair"]
    return ZFIELDS_BY_PART["unknown"]
