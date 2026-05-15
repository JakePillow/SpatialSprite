from __future__ import annotations

import sys
from pathlib import Path

workspace_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_root / "tool"))

from spritespatial.image_loader import mirror_sprite_to_left_right


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: python tools/mirror_directional_sprite.py <source.png> <left.png> <right.png>")
        return 1

    source = Path(sys.argv[1])
    left_target = Path(sys.argv[2])
    right_target = Path(sys.argv[3])

    if not source.exists():
        print(f"Source file not found: {source}")
        return 2

    mirror_sprite_to_left_right(source, left_target, right_target)

    print(f"Created side sprites from {source}:")
    print(f"  left mirrored: {left_target}")
    print(f"  right source:  {right_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
