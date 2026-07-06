from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from spritespatial.validation import ValidationReport

DEPTH_FIELD_SCHEMA_VERSION = "spritespatial_depth_field_v1"


@dataclass(frozen=True)
class PipelineVersions:
    pipeline_version: str = "0.4.0"
    semantic_version: str = "0.2.1"
    depth_version: str = "0.3.0"
    mesher_version: str = "0.1.0"


@dataclass(frozen=True)
class DepthProfile:
    semantic_class: str
    profile: str
    max_depth_factor: float
    anisotropy: tuple[float, float] = (1.0, 1.0)
    blend_radius_px: int = 1
    silhouette_pin: bool = True
    back_scale: float = 1.0
    global_weight: float = 0.25
    region_weight: float = 0.75
    local_detail_weight: float = 0.0
    layer: str = "region"
    primitive_hint: str = "rounded_cuboid"
    depth_priority: int = 50
    explicit: bool = True

    @classmethod
    def from_mapping(
        cls, semantic_class: str, payload: dict[str, Any], *, explicit: bool = True
    ) -> "DepthProfile":
        anisotropy = payload.get("anisotropy", (1.0, 1.0))
        if not isinstance(anisotropy, (list, tuple)) or len(anisotropy) != 2:
            raise ValueError(f"{semantic_class}.anisotropy must contain x and y radii")
        return cls(
            semantic_class=semantic_class,
            profile=str(payload.get("profile", "linear")),
            max_depth_factor=float(payload.get("max_depth_factor", 0.20)),
            anisotropy=(max(float(anisotropy[0]), 1e-4), max(float(anisotropy[1]), 1e-4)),
            blend_radius_px=max(0, int(payload.get("blend_radius_px", 1))),
            silhouette_pin=bool(payload.get("silhouette_pin", True)),
            back_scale=max(0.0, float(payload.get("back_scale", 1.0))),
            global_weight=max(0.0, float(payload.get("global_weight", 0.25))),
            region_weight=max(0.0, float(payload.get("region_weight", 0.75))),
            local_detail_weight=max(0.0, float(payload.get("local_detail_weight", 0.0))),
            layer=str(payload.get("layer", "region")),
            primitive_hint=str(payload.get("primitive_hint", "rounded_cuboid")),
            depth_priority=int(payload.get("depth_priority", 50)),
            explicit=explicit,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["anisotropy"] = list(self.anisotropy)
        return payload


@dataclass(frozen=True)
class SemanticRegion:
    region_id: str
    semantic_class: str
    mask: np.ndarray


@dataclass(frozen=True)
class SpriteDepthAsset:
    asset_id: str
    alpha_mask: np.ndarray


@dataclass(frozen=True)
class DepthConfig:
    max_total_depth: float = 0.60
    profile_pack: str = "humanoid_default_v2"
    profile_registry: Any | None = None
    versions: PipelineVersions = field(default_factory=PipelineVersions)
    join_discontinuity_threshold: float = 0.14
    detail_depth_threshold: float = 0.18
    spike_sigma: float = 3.0
    output_dir: Path | None = None
    emit_debug: bool = True


@dataclass(frozen=True)
class BlendJunction:
    class_a: str
    class_b: str
    pixel_count: int
    max_discontinuity_before: float
    max_discontinuity_after: float


@dataclass(frozen=True)
class RegionDepthDiagnostics:
    region_id: str
    semantic_class: str
    profile_name: str
    max_depth: float
    actual_depth_min: float
    actual_depth_max: float
    actual_depth_mean: float
    silhouette_pin_passed: bool
    spike_count: int
    continuity_score: float
    primitive_residual_estimate: float
    explicit_profile: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DepthDiagnostics:
    regions: tuple[RegionDepthDiagnostics, ...]
    silhouette_pin_passed: bool
    isolated_spike_count: int
    join_discontinuity_max: float
    assigned_pixel_count: int
    opaque_pixel_count: int


@dataclass
class DepthFieldResult:
    asset_id: str
    versions: PipelineVersions
    profile_pack: str
    region_depth_fields: dict[str, np.ndarray]
    plain_edt_fields: dict[str, np.ndarray]
    anisotropic_edt_fields: dict[str, np.ndarray]
    global_depth_field: np.ndarray
    blended_depth_field: np.ndarray
    pinned_depth_field: np.ndarray
    region_profiles: dict[str, DepthProfile]
    blend_junctions: list[BlendJunction]
    silhouette_mask: np.ndarray
    alpha_mask: np.ndarray
    diagnostics: DepthDiagnostics
    validation: ValidationReport
    artifact_paths: dict[str, Path] = field(default_factory=dict)

    @property
    def pipeline_version(self) -> str:
        return self.versions.pipeline_version

    @property
    def semantic_version(self) -> str:
        return self.versions.semantic_version

    @property
    def depth_version(self) -> str:
        return self.versions.depth_version

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "schema": DEPTH_FIELD_SCHEMA_VERSION,
            "asset_id": self.asset_id,
            **asdict(self.versions),
            "profile_pack": self.profile_pack,
            "shape": list(self.pinned_depth_field.shape),
            "region_profiles": {
                key: profile.to_dict() for key, profile in self.region_profiles.items()
            },
            "blend_junctions": [asdict(junction) for junction in self.blend_junctions],
            "diagnostics": {
                **asdict(self.diagnostics),
                "regions": [asdict(region) for region in self.diagnostics.regions],
            },
            "validation": self.validation.to_dict(),
            "artifacts": {key: str(path) for key, path in self.artifact_paths.items()},
        }
