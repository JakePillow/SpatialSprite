from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from PIL import Image

from spritespatial.depthfields.anisotropic import anisotropic_edt
from spritespatial.depthfields.blending import blend_semantic_junctions
from spritespatial.depthfields.diagnostics import build_diagnostics
from spritespatial.depthfields.edt import euclidean_distance_transform, normalise_distance
from spritespatial.depthfields.pinning import pin_silhouette
from spritespatial.depthfields.profile_registry import DepthProfileRegistry, load_profile_registry
from spritespatial.depthfields.schema import DepthConfig, DepthFieldResult, SemanticRegion, SpriteDepthAsset
from spritespatial.depthfields.validation import validate_depth_field


def generate_depth_field(
    sprite_asset: SpriteDepthAsset | Image.Image | np.ndarray | Mapping[str, Any],
    semantic_hierarchy: Iterable[SemanticRegion | Mapping[str, Any]] | Mapping[Any, Any],
    depth_config: DepthConfig | Mapping[str, Any] | None = None,
) -> DepthFieldResult:
    """Generate the authoritative layered depth field before primitive fitting."""
    config = _coerce_config(depth_config)
    asset = _coerce_asset(sprite_asset)
    alpha = np.asarray(asset.alpha_mask, dtype=bool)
    registry = _registry(config)
    regions = _coerce_regions(semantic_hierarchy, alpha)
    assigned = np.zeros(alpha.shape, dtype=bool)
    for region in regions:
        assigned |= region.mask
    if bool(np.any(alpha & ~assigned)):
        regions.append(SemanticRegion("unassigned", "unknown", alpha & ~assigned))

    profiles = {region.region_id: registry.get(region.semantic_class) for region in regions}
    constraints = np.zeros(alpha.shape, dtype=bool)
    for region in regions:
        if profiles[region.region_id].layer == "constraint":
            constraints |= region.mask
    geometry_mask = alpha & ~constraints
    body_edt = euclidean_distance_transform(geometry_mask)
    body_norm = normalise_distance(body_edt, geometry_mask)
    global_depth = (_profile_shape(body_norm, "cosine") * config.max_total_depth).astype(np.float32)
    global_depth[~geometry_mask] = 0.0

    region_fields: dict[str, np.ndarray] = {}
    plain_fields: dict[str, np.ndarray] = {}
    anisotropic_fields: dict[str, np.ndarray] = {}
    labels = np.full(alpha.shape, "", dtype=object)
    composed = np.zeros(alpha.shape, dtype=np.float32)
    region_masks: dict[str, np.ndarray] = {}

    ordered = sorted(regions, key=lambda region: profiles[region.region_id].depth_priority)
    for region in ordered:
        mask = np.asarray(region.mask, dtype=bool) & alpha
        region_masks[region.region_id] = mask
        profile = profiles[region.region_id]
        plain = normalise_distance(euclidean_distance_transform(mask), mask)
        anisotropic = normalise_distance(anisotropic_edt(mask, profile.anisotropy), mask)
        local = (
            _profile_shape(anisotropic, profile.profile)
            * min(profile.max_depth_factor, config.max_total_depth)
        ).astype(np.float32)
        local[~mask] = 0.0
        if profile.layer == "constraint":
            local[:] = 0.0
        plain_fields[region.region_id] = plain
        anisotropic_fields[region.region_id] = anisotropic
        region_fields[region.region_id] = local

        total_weight = max(
            profile.global_weight + profile.region_weight + profile.local_detail_weight,
            1.0,
        )
        candidate = (
            profile.global_weight * global_depth
            + profile.region_weight * local
            + profile.local_detail_weight * local
        ) / total_weight
        composed[mask] = candidate[mask]
        labels[mask] = profile.semantic_class

    composed[~alpha] = 0.0
    composed[constraints] = 0.0
    radii = {profile.semantic_class: profile.blend_radius_px for profile in profiles.values()}
    blended, junctions = blend_semantic_junctions(composed, labels, alpha, radii, constraints)
    pinned, seam = pin_silhouette(blended, alpha, constraints)
    np.clip(pinned, 0.0, config.max_total_depth, out=pinned)
    validation = validate_depth_field(
        pinned, alpha, seam, profiles, region_masks, junctions, config
    )
    max_join = max((junction.max_discontinuity_after for junction in junctions), default=0.0)
    diagnostics = build_diagnostics(
        pinned, alpha, seam, region_masks, profiles, labels, max_join, config.spike_sigma
    )
    result = DepthFieldResult(
        asset_id=asset.asset_id,
        versions=config.versions,
        profile_pack=registry.name,
        region_depth_fields=region_fields,
        plain_edt_fields=plain_fields,
        anisotropic_edt_fields=anisotropic_fields,
        global_depth_field=global_depth,
        blended_depth_field=blended,
        pinned_depth_field=pinned,
        region_profiles=profiles,
        blend_junctions=junctions,
        silhouette_mask=seam,
        alpha_mask=alpha,
        diagnostics=diagnostics,
        validation=validation,
    )
    if config.output_dir is not None:
        from spritespatial.depthfields.report import write_depth_result

        write_depth_result(result, config.output_dir, emit_debug=config.emit_debug)
    return result


def _coerce_config(value: DepthConfig | Mapping[str, Any] | None) -> DepthConfig:
    if value is None:
        return DepthConfig()
    if isinstance(value, DepthConfig):
        return value
    if isinstance(value, Mapping):
        return DepthConfig(**dict(value))
    raise TypeError("depth_config must be DepthConfig, a mapping, or None")


def _registry(config: DepthConfig) -> DepthProfileRegistry:
    source = config.profile_registry
    if source is None and config.profile_pack and Path(config.profile_pack).suffix:
        source = config.profile_pack
    registry = load_profile_registry(source)
    if source is None and config.profile_pack != registry.name:
        registry.name = config.profile_pack
    return registry


def _coerce_asset(
    value: SpriteDepthAsset | Image.Image | np.ndarray | Mapping[str, Any]
) -> SpriteDepthAsset:
    if isinstance(value, SpriteDepthAsset):
        return replace(value, alpha_mask=np.asarray(value.alpha_mask, dtype=bool))
    if isinstance(value, Image.Image):
        alpha = np.asarray(value.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0
        return SpriteDepthAsset("sprite", alpha)
    if isinstance(value, np.ndarray):
        array = np.asarray(value)
        mask = array if array.ndim == 2 else array[:, :, 3] > 0
        return SpriteDepthAsset("sprite", np.asarray(mask, dtype=bool))
    if isinstance(value, Mapping):
        mask = value.get("alpha_mask", value.get("mask"))
        if mask is None and isinstance(value.get("image"), Image.Image):
            image_asset = _coerce_asset(value["image"])
            return replace(image_asset, asset_id=str(value.get("asset_id", "sprite")))
        if mask is None:
            raise ValueError("sprite_asset mapping requires alpha_mask, mask, or image")
        return SpriteDepthAsset(str(value.get("asset_id", "sprite")), np.asarray(mask, dtype=bool))
    raise TypeError(f"Unsupported sprite asset: {type(value).__name__}")


def _coerce_regions(
    value: Iterable[SemanticRegion | Mapping[str, Any]] | Mapping[Any, Any],
    alpha: np.ndarray,
) -> list[SemanticRegion]:
    if isinstance(value, Mapping) and "regions" in value:
        value = value["regions"]
    if isinstance(value, Mapping):
        if all(isinstance(key, tuple) and len(key) == 2 for key in value):
            labels: dict[str, np.ndarray] = {}
            for (x, y), label in value.items():
                if 0 <= int(y) < alpha.shape[0] and 0 <= int(x) < alpha.shape[1]:
                    labels.setdefault(str(label), np.zeros(alpha.shape, dtype=bool))[int(y), int(x)] = True
            return [
                SemanticRegion(f"region_{index:03d}_{_safe(label)}", label, mask & alpha)
                for index, (label, mask) in enumerate(labels.items())
            ]
        value = list(value.values())
    regions: list[SemanticRegion] = []
    for index, item in enumerate(value):
        if isinstance(item, SemanticRegion):
            region = replace(item, mask=np.asarray(item.mask, dtype=bool) & alpha)
        else:
            semantic_class = str(
                item.get("semantic_class", item.get("semantic_label", item.get("name", "unknown")))
            )
            region_id = str(
                item.get("region_id", item.get("id", f"region_{index:03d}_{_safe(semantic_class)}"))
            )
            if item.get("mask") is not None:
                mask = np.asarray(item["mask"], dtype=bool)
            else:
                mask = np.zeros(alpha.shape, dtype=bool)
                for x, y in item.get("pixels", set()):
                    if 0 <= int(y) < alpha.shape[0] and 0 <= int(x) < alpha.shape[1]:
                        mask[int(y), int(x)] = True
            region = SemanticRegion(region_id, semantic_class, mask & alpha)
        if region.mask.shape != alpha.shape:
            raise ValueError(
                f"Region {region.region_id} mask shape {region.mask.shape} does not match alpha {alpha.shape}"
            )
        if region.mask.any():
            regions.append(region)
    return regions


def _profile_shape(values: np.ndarray, profile: str) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    name = str(profile).lower()
    if name in {"linear", "hard", "wedge"}:
        return clipped
    if name in {"convex", "capsule", "capsule_chain", "tapered_capsule_chain"}:
        return clipped ** 0.65
    if name in {"concave", "concave_shell", "shell_offset"}:
        return clipped ** 1.8
    if name in {"cosine", "hemisphere", "rounded_front", "rounded_cuboid"}:
        return 0.5 - 0.5 * np.cos(math.pi * clipped)
    if name in {"plateau", "flattened_rounded_box"}:
        return np.minimum(1.0, clipped * 1.8)
    return clipped


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_").lower() or "unknown"
