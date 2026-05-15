from __future__ import annotations

import sys
from pathlib import Path

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "tool"))
from spritespatial.asset_schema import AssetSchema
from spritespatial.validators import inspect_png


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: python tools/preflight_check.py <path/to/spriteasset_v1.json> [<path/to/Godot.exe>]")
        return 2

    schema_path = Path(argv[0]).resolve()
    godot_path = Path(argv[1]).resolve() if len(argv) > 1 else None

    if not schema_path.exists():
        print(f"Asset schema not found: {schema_path}")
        return 3

    try:
        asset = AssetSchema.load_from_file(schema_path)
    except Exception as e:
        print(f"Failed to load asset schema: {e}")
        return 4

    print(f"Loaded asset schema: {asset.asset_name} (render_mode={asset.render_mode})")

    ok = True
    for direction in asset.source_sprites:
        p = asset.sprite_path(direction)
        if not p.exists():
            print(f"MISSING: {direction} -> {p}")
            ok = False
            continue
        try:
            w, h, alpha = inspect_png(p)
        except Exception as e:
            print(f"ERROR reading {p}: {e}")
            ok = False
            continue
        print(f"{direction}: {p.name} {w}x{h} alpha={'yes' if alpha else 'NO'}")

    if godot_path:
        print(f"Checking Godot executable: {godot_path}")
        if godot_path.exists():
            print("Godot executable found.")
        else:
            print("Godot executable NOT found. Provide correct path to Godot.exe.")
            ok = False

    if ok:
        print("Preflight check passed.")
        return 0
    else:
        print("Preflight check failed. Fix listed issues and retry.")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
