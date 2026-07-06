from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from spritespatial.depthfields.schema import DepthConfig, DepthFieldResult
from spritespatial.pipeline_models import MeshAsset, PrimitiveSet, SignedDistanceVolume
from spritespatial.validation import ValidationReport


@runtime_checkable
class DepthGenerator(Protocol):
    def generate(
        self, sprite_asset: Any, semantic_hierarchy: Any, config: DepthConfig
    ) -> DepthFieldResult: ...


@runtime_checkable
class PrimitiveFitter(Protocol):
    def fit(self, depth: DepthFieldResult, config: Any) -> PrimitiveSet: ...


@runtime_checkable
class VolumeSynthesizer(Protocol):
    def synthesize(
        self, depth: DepthFieldResult, primitives: PrimitiveSet, config: Any
    ) -> SignedDistanceVolume: ...


@runtime_checkable
class Mesher(Protocol):
    def mesh(self, volume: SignedDistanceVolume, config: Any) -> MeshAsset: ...


@runtime_checkable
class Validator(Protocol):
    def validate(self, artifact: Any, config: Any) -> ValidationReport: ...


@runtime_checkable
class Exporter(Protocol):
    def export(self, mesh: MeshAsset, output_dir: Path, config: Any) -> dict[str, Path]: ...
