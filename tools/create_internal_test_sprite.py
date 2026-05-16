from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a controlled 16x24 humanoid topology test sprite.")
    parser.add_argument("-o", "--output", type=Path, default=WORKSPACE_ROOT / "assets" / "samples" / "internal" / "topology_humanoid_front.png")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sprite = build_sprite()
    sprite.save(output, format="PNG")
    print(f"Wrote internal topology test sprite: {output}")
    return 0


def build_sprite() -> Image.Image:
    image = Image.new("RGBA", (16, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outline = (24, 24, 24, 255)
    skin = (232, 160, 104, 255)
    hair = (96, 64, 40, 255)
    shirt = (64, 168, 208, 255)
    pants = (56, 96, 184, 255)
    boots = (136, 72, 48, 255)

    # Head.
    draw.rectangle((5, 2, 10, 7), fill=outline)
    draw.rectangle((6, 3, 9, 6), fill=skin)
    draw.rectangle((6, 2, 9, 3), fill=hair)

    # Torso.
    draw.rectangle((4, 8, 11, 14), fill=outline)
    draw.rectangle((5, 9, 10, 13), fill=shirt)

    # Arms.
    draw.rectangle((2, 9, 4, 15), fill=outline)
    draw.rectangle((3, 10, 3, 14), fill=skin)
    draw.rectangle((11, 9, 13, 15), fill=outline)
    draw.rectangle((12, 10, 12, 14), fill=skin)

    # Legs.
    draw.rectangle((5, 14, 7, 21), fill=outline)
    draw.rectangle((6, 15, 6, 19), fill=pants)
    draw.rectangle((8, 14, 10, 21), fill=outline)
    draw.rectangle((9, 15, 9, 19), fill=pants)

    # Boots.
    draw.rectangle((4, 20, 7, 22), fill=outline)
    draw.rectangle((5, 20, 7, 21), fill=boots)
    draw.rectangle((8, 20, 11, 22), fill=outline)
    draw.rectangle((8, 20, 10, 21), fill=boots)
    return image


if __name__ == "__main__":
    raise SystemExit(main())
