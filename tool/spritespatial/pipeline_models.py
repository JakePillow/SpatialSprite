from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from spritespatial.depthfields.schema import DepthFieldResult, PipelineVersions
from spritespatial.validation import ValidationReport


@dataclass(frozen=True)
class ArtifactMetadata:
    asset_id: str
    versions: PipelineVersions = field(default_factory=PipelineVersions)
    profile_pack: str = "humanoid_default_v2"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["versions"] = asdict(self.versions)
        return payload


@dataclass(frozen=True)
class SpriteAsset:
    metadata: ArtifactMetadata
    source_sprites: dict[str, str]
    width: int
    height: int
    alpha_threshold: int = 16


@dataclass(frozen=True)
class PaletteMap:
    metadata: ArtifactMetadata
    colours: tuple[tuple[int, int, int, int], ...]
    pixel_palette_indices: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class SemanticRegion:
    region_id: str
    semantic_class: str
    pixel_count: int
    parent_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticHierarchy:
    metadata: ArtifactMetadata
    regions: tuple[SemanticRegion, ...]


@dataclass(frozen=True)
class PrimitiveSet:
    metadata: ArtifactMetadata
    primitives: tuple[dict[str, Any], ...]
    residual_by_region: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SignedDistanceVolume:
    metadata: ArtifactMetadata
    shape: tuple[int, int, int]
    voxel_size: float
    data_path: str


@dataclass(frozen=True)
class MeshAsset:
    metadata: ArtifactMetadata
    vertices: tuple[tuple[float, float, float], ...]
    indices: tuple[int, ...]
    normals: tuple[tuple[float, float, float], ...] = ()


@dataclass(frozen=True)
class BuildRun:
    metadata: ArtifactMetadata
    depth: DepthFieldResult | None = None
    primitives: PrimitiveSet | None = None
    volume: SignedDistanceVolume | None = None
    mesh: MeshAsset | None = None
    validation: ValidationReport | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
