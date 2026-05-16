from __future__ import annotations

import sys
from pathlib import Path

# Ensure the sprite tool package can be imported when running from the repo root.
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.asset_schema import AssetSchema  # noqa: E402
from spritespatial.godot_exporter import generate_gdscript, generate_scene_file  # noqa: E402
from spritespatial.validators import validate_asset_schema  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/build_sprite_asset.py <path/to/spriteasset_v1.json>")
        return 1

    asset_schema_path = Path(sys.argv[1])
    if not asset_schema_path.is_absolute():
        asset_schema_path = Path.cwd() / asset_schema_path
    asset_schema_path = asset_schema_path.resolve()

    if not asset_schema_path.exists():
        print(f"Asset schema not found: {asset_schema_path}")
        return 2

    asset = AssetSchema.load_from_file(asset_schema_path)
    validate_asset_schema(asset)

    output_dir = WORKSPACE_ROOT / "outputs" / asset.asset_name
    output_dir.mkdir(parents=True, exist_ok=True)

    script_path = output_dir / "directional_sprite_3d.gd"
    scene_path = output_dir / f"{asset.asset_name}.tscn"

    generate_gdscript(script_path)
    generate_scene_file(scene_path, script_path, asset, WORKSPACE_ROOT)

    print(f"Built sprite asset '{asset.asset_name}' to: {output_dir}")
    print(f"  Scene: {scene_path}")
    print(f"  Script: {script_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
