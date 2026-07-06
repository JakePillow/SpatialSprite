from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from spritespatial.depthfields.profiles import DEFAULT_PROFILE_DEFINITIONS, PROFILE_ALIASES
from spritespatial.depthfields.schema import DepthProfile


class DepthProfileRegistry:
    def __init__(
        self,
        definitions: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        name: str = "humanoid_default_v2",
        aliases: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        source = definitions or DEFAULT_PROFILE_DEFINITIONS
        self._definitions = {str(key).upper(): dict(value) for key, value in source.items()}
        custom_aliases = {str(key).lower(): str(value).upper() for key, value in (aliases or {}).items()}
        self._aliases = {**PROFILE_ALIASES, **custom_aliases}
        self._resolved: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_json(cls, path: Path) -> "DepthProfileRegistry":
        data = json.loads(path.read_text(encoding="utf-8"))
        definitions = data.get("profiles", data.get("definitions", {}))
        if not isinstance(definitions, dict):
            raise ValueError(f"Depth profile registry profiles must be an object: {path}")
        converted: dict[str, dict[str, Any]] = {}
        for key, raw in definitions.items():
            payload = dict(raw)
            if "profile_type" in payload and "profile" not in payload:
                payload["profile"] = payload["profile_type"]
            if "half_thickness_fraction" in payload and "max_depth_factor" not in payload:
                payload["max_depth_factor"] = payload["half_thickness_fraction"]
            converted[str(key).upper()] = payload
        merged = deepcopy(DEFAULT_PROFILE_DEFINITIONS)
        merged.update(converted)
        return cls(merged, name=str(data.get("name", path.stem)), aliases=data.get("aliases", {}))

    def canonical_class(self, semantic_class: str) -> tuple[str, bool]:
        raw = str(semantic_class or "unknown").strip()
        upper = raw.upper()
        if upper in self._definitions:
            return upper, True
        alias = self._aliases.get(raw.lower())
        if alias and alias in self._definitions:
            return alias, True
        return "UNKNOWN", False

    def get(self, semantic_class: str) -> DepthProfile:
        canonical, explicit = self.canonical_class(semantic_class)
        return DepthProfile.from_mapping(canonical, self._resolve(canonical, set()), explicit=explicit)

    def _resolve(self, semantic_class: str, stack: set[str]) -> dict[str, Any]:
        if semantic_class in self._resolved:
            return dict(self._resolved[semantic_class])
        if semantic_class in stack:
            raise ValueError(f"Depth profile inheritance cycle at {semantic_class}")
        raw = dict(self._definitions[semantic_class])
        parent = raw.pop("extends", None)
        resolved: dict[str, Any] = {}
        if parent:
            resolved.update(self._resolve(str(parent).upper(), stack | {semantic_class}))
        resolved.update(raw)
        self._resolved[semantic_class] = resolved
        return dict(resolved)


def load_profile_registry(source: Any | None = None) -> DepthProfileRegistry:
    if isinstance(source, DepthProfileRegistry):
        return source
    if source is None:
        return DepthProfileRegistry()
    if isinstance(source, (str, Path)):
        return DepthProfileRegistry.from_json(Path(source))
    if isinstance(source, Mapping):
        definitions = source.get("profiles", source.get("definitions", source))
        return DepthProfileRegistry(
            definitions,
            name=str(source.get("name", "custom")),
            aliases=source.get("aliases", {}),
        )
    raise TypeError(f"Unsupported depth profile registry: {type(source).__name__}")
