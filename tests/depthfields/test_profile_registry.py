from spritespatial.depthfields.profile_registry import DepthProfileRegistry


def test_profile_inheritance_and_aliases() -> None:
    registry = DepthProfileRegistry()
    head = registry.get("head")
    hair = registry.get("hair/hat")
    weapon = registry.get("sword")
    assert head.semantic_class == "HEAD"
    assert head.profile == "cosine"
    assert head.global_weight == 0.25
    assert hair.local_detail_weight == 0.40
    assert weapon.primitive_hint == "plate"


def test_unknown_label_is_auditable_fallback() -> None:
    profile = DepthProfileRegistry().get("unclassified_glow")
    assert profile.semantic_class == "UNKNOWN"
    assert profile.explicit is False
