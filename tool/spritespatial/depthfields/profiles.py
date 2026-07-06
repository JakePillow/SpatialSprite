from __future__ import annotations

DEFAULT_PROFILE_DEFINITIONS: dict[str, dict[str, object]] = {
    "BODY_PART": {
        "profile": "cosine", "max_depth_factor": 0.32, "anisotropy": [1.0, 1.0],
        "blend_radius_px": 2, "silhouette_pin": True, "back_scale": 0.88,
        "global_weight": 0.25, "region_weight": 0.75, "local_detail_weight": 0.0,
        "layer": "region", "primitive_hint": "rounded_cuboid", "depth_priority": 60,
    },
    "SHELL_PART": {
        "profile": "concave_shell", "max_depth_factor": 0.14, "anisotropy": [1.8, 0.5],
        "blend_radius_px": 2, "silhouette_pin": True, "back_scale": 0.35,
        "global_weight": 0.05, "region_weight": 0.55, "local_detail_weight": 0.40,
        "layer": "region", "primitive_hint": "shell", "depth_priority": 80,
    },
    "HARD_PROP": {
        "profile": "linear", "max_depth_factor": 0.16, "anisotropy": [2.2, 0.35],
        "blend_radius_px": 1, "silhouette_pin": True, "back_scale": 0.55,
        "global_weight": 0.0, "region_weight": 0.85, "local_detail_weight": 0.15,
        "layer": "region", "primitive_hint": "plate", "depth_priority": 90,
    },
    "LOCAL_DETAIL": {
        "profile": "plateau", "max_depth_factor": 0.08, "anisotropy": [1.0, 1.0],
        "blend_radius_px": 1, "silhouette_pin": True, "back_scale": 0.25,
        "global_weight": 0.0, "region_weight": 0.20, "local_detail_weight": 0.80,
        "layer": "detail", "primitive_hint": "surface_detail", "depth_priority": 100,
    },
    "HEAD": {"extends": "BODY_PART", "max_depth_factor": 0.45, "anisotropy": [1.8, 0.6], "primitive_hint": "ellipsoid", "depth_priority": 90},
    "FACE": {"extends": "LOCAL_DETAIL", "max_depth_factor": 0.12, "profile": "cosine", "anisotropy": [1.5, 0.55]},
    "TORSO": {"extends": "BODY_PART", "max_depth_factor": 0.40, "anisotropy": [1.35, 0.8], "global_weight": 0.30, "region_weight": 0.65, "local_detail_weight": 0.05},
    "ARM": {"extends": "BODY_PART", "profile": "convex", "max_depth_factor": 0.30, "anisotropy": [0.65, 1.8], "global_weight": 0.15, "region_weight": 0.80, "local_detail_weight": 0.05, "primitive_hint": "capsule"},
    "LEG": {"extends": "ARM", "max_depth_factor": 0.34, "anisotropy": [0.55, 2.0], "primitive_hint": "tapered_capsule"},
    "FOOT": {"extends": "BODY_PART", "profile": "plateau", "max_depth_factor": 0.18, "anisotropy": [1.9, 0.55], "primitive_hint": "rounded_box", "depth_priority": 74},
    "HAIR": {"extends": "SHELL_PART", "max_depth_factor": 0.12, "anisotropy": [2.0, 0.4]},
    "CAPE": {"extends": "SHELL_PART", "max_depth_factor": 0.10, "anisotropy": [1.4, 0.45]},
    "CLOTH": {"extends": "SHELL_PART", "profile": "concave", "max_depth_factor": 0.11},
    "WEAPON": {"extends": "HARD_PROP", "max_depth_factor": 0.14},
    "SHIELD": {"extends": "HARD_PROP", "profile": "plateau", "max_depth_factor": 0.18, "anisotropy": [1.0, 1.0]},
    "ARMOUR": {"extends": "HARD_PROP", "profile": "plateau", "max_depth_factor": 0.16},
    "EYE_DETAIL": {"extends": "LOCAL_DETAIL", "max_depth_factor": 0.05},
    "OUTLINE": {"extends": "LOCAL_DETAIL", "profile": "linear", "max_depth_factor": 0.0, "global_weight": 0.0, "region_weight": 0.0, "local_detail_weight": 0.0, "layer": "constraint", "primitive_hint": "none", "depth_priority": 1000},
    "UNKNOWN": {"extends": "BODY_PART", "profile": "linear", "max_depth_factor": 0.20, "depth_priority": 1},
}

PROFILE_ALIASES = {
    "head": "HEAD", "face": "FACE", "torso": "TORSO",
    "left_arm": "ARM", "right_arm": "ARM", "arm": "ARM",
    "left_leg": "LEG", "right_leg": "LEG", "legs": "LEG", "leg": "LEG",
    "boots/feet": "FOOT", "boots_feet": "FOOT", "boots": "FOOT", "feet": "FOOT",
    "hair/hat": "HAIR", "hat_hair": "HAIR", "hair": "HAIR", "hat": "HAIR",
    "cape": "CAPE", "cloth": "CLOTH", "clothing": "CLOTH",
    "equipment/shield/sword": "WEAPON", "equipment": "WEAPON", "sword": "WEAPON",
    "weapon": "WEAPON", "weapon_blade": "WEAPON", "shield": "SHIELD",
    "armour": "ARMOUR", "armor": "ARMOUR", "eye_detail": "EYE_DETAIL",
    "eyes": "EYE_DETAIL", "outline": "OUTLINE", "unknown": "UNKNOWN",
}
