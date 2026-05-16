# Godot 4 Pixel Sprite Import Baseline

SpriteSpatial pixel assets should stay crisp in Godot. Use these import settings for source PNGs used by `Sprite3D`.

## Texture Import Settings

- Compression Mode: `Lossless`
- Mipmaps: `Off` for near/mid prototype tests
- Repeat: `Disabled`
- Fix Alpha Border: `Enabled`
- Premult Alpha: `Disabled` by default
- Process mode: preserve RGBA channels

In the Godot Import dock, this corresponds to:

```text
compress/mode=0
mipmaps/generate=false
process/fix_alpha_border=true
process/premult_alpha=false
```

## Sprite3D Settings

Generated SpriteSpatial `Sprite3D` nodes should request nearest filtering:

```gdscript
sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
```

The generated scenes also set:

```text
texture_filter = 0
```

## Notes

- Do not use JPG for source sprites or extracted sprites.
- Keep extracted sprites as PNG with alpha.
- If testing long-distance rendering later, evaluate mipmaps separately; keep them off for current near/mid tests.
