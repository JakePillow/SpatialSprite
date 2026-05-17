from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a controlled non-humanoid topology regression sprite.")
    parser.add_argument("-o", "--output", type=Path, default=WORKSPACE_ROOT / "assets" / "samples" / "internal" / "topology_enemy_front.png")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sprite = build_sprite()
    sprite.save(output, format="PNG")
    print(f"Wrote enemy topology test sprite: {output}")
    return 0


def build_sprite() -> Image.Image:
    image = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outline = (22, 22, 22, 255)
    body = (112, 196, 82, 255)
    belly = (178, 224, 116, 255)
    eye = (246, 240, 210, 255)
    foot = (82, 126, 54, 255)

    # Rounded simple enemy/blob with appendages. It deliberately does not fit
    # the humanoid rule set cleanly, so semantic warnings remain meaningful.
    draw.rectangle((5, 2, 12, 3), fill=outline)
    draw.rectangle((3, 4, 14, 11), fill=outline)
    draw.rectangle((4, 3, 13, 12), fill=body)
    draw.rectangle((5, 5, 12, 10), fill=belly)
    draw.rectangle((5, 4, 6, 5), fill=eye)
    draw.rectangle((11, 4, 12, 5), fill=eye)
    draw.rectangle((4, 11, 7, 14), fill=outline)
    draw.rectangle((5, 11, 7, 13), fill=foot)
    draw.rectangle((10, 11, 13, 14), fill=outline)
    draw.rectangle((10, 11, 12, 13), fill=foot)
    draw.rectangle((1, 7, 3, 9), fill=outline)
    draw.rectangle((14, 7, 16, 9), fill=outline)
    return image


if __name__ == "__main__":
    raise SystemExit(main())
