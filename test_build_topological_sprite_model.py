from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


WORKSPACE_ROOT = Path(__file__).resolve().parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
TOOLS_ROOT = WORKSPACE_ROOT / "tools"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from build_topological_sprite_model import (  # noqa: E402
    _depth_multiplier_for_part,
    _build_front_led_voxel_occupancy,
    _relief_face_colour,
    _rgba_float,
    _vibrant_side_colour,
    _zfield_face_colour,
)


def _assert_float_list_close(test_case: unittest.TestCase, actual: list[float], expected: list[float]) -> None:
    test_case.assertEqual(len(actual), len(expected))
    for actual_value, expected_value in zip(actual, expected):
        test_case.assertAlmostEqual(actual_value, expected_value, places=6)


class TopologicalSpriteModelTests(unittest.TestCase):
    def test_side_envelope_can_only_trim_voxel_depth(self) -> None:
        front = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
        side = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
        for y in range(1, 6):
            for x in range(1, 6):
                front.putpixel((x, y), (220, 40, 80, 255))
            side.putpixel((3, y), (220, 40, 80, 255))
            side.putpixel((4, y), (220, 40, 80, 255))
        for x in range(2, 5):
            side.putpixel((x, 1), (220, 40, 80, 255))
            side.putpixel((x, 5), (220, 40, 80, 255))
        source = np.zeros((7, 7, 15), dtype=bool)
        source[1:6, 1:6, 4:11] = True

        uncapped, _ = _build_front_led_voxel_occupancy(front, source)
        capped, report = _build_front_led_voxel_occupancy(front, source, side=side)

        self.assertTrue(np.all(capped <= uncapped))
        self.assertTrue(np.array_equal(capped.any(axis=2), uncapped.any(axis=2)))
        self.assertLess(int(capped[3].sum()), int(uncapped[3].sum()))
        self.assertTrue(report["side_view_depth_cap_used"])
        self.assertFalse(report["side_view_voxels_added"])

    def test_front_led_voxel_occupancy_uses_local_relief_and_ignores_back_only_support(self) -> None:
        image = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
        for y in range(1, 6):
            for x in range(1, 6):
                image.putpixel((x, y), (220, 40, 80, 255))
        image.putpixel((3, 3), (248, 208, 192, 255))
        source = np.zeros((7, 7, 15), dtype=bool)
        source[1:6, 1:6, 4:11] = True
        source[0, 0, 4:11] = True

        occupancy, report = _build_front_led_voxel_occupancy(image, source)

        self.assertFalse(occupancy[0, 0, :].any())
        self.assertTrue(np.array_equal(occupancy.any(axis=2), np.asarray(image)[:, :, 3] > 16))
        self.assertGreater(int(occupancy[3, 3, :].sum()), int(occupancy[1, 1, :].sum()))
        occupied_columns = occupancy[np.asarray(image)[:, :, 3] > 16]
        self.assertTrue(
            all(
                np.all(column[np.flatnonzero(column)[0] : np.flatnonzero(column)[-1] + 1])
                for column in occupied_columns
            )
        )
        self.assertEqual(report["geometry_authority"], "front_alpha_local_colour_relief")
        self.assertFalse(report["side_view_geometry_used"])

    def test_rgba_float_converts_correctly(self) -> None:
        _assert_float_list_close(self, _rgba_float((255, 128, 0, 255)), [1.0, 128 / 255.0, 0.0, 1.0])
        _assert_float_list_close(self, _rgba_float((0, 0, 0, 0)), [0.0, 0.0, 0.0, 0.0])

    def test_vibrant_side_colour_darkens_bright_colours(self) -> None:
        factor = 0.75
        expected = [(200 * factor) / 255.0, (50 * factor) / 255.0, (50 * factor) / 255.0, 1.0]
        _assert_float_list_close(self, _vibrant_side_colour((200, 50, 50, 255)), expected)

    def test_vibrant_side_colour_applies_less_darkening_for_dark_colours(self) -> None:
        factor = 0.9
        expected = [(40 * factor) / 255.0, (40 * factor) / 255.0, (48 * factor) / 255.0, 1.0]
        _assert_float_list_close(self, _vibrant_side_colour((40, 40, 48, 255)), expected)

    def test_vibrant_side_colour_handles_black(self) -> None:
        _assert_float_list_close(self, _vibrant_side_colour((0, 0, 0, 255)), [0.0, 0.0, 0.0, 1.0])

    def test_relief_face_colour_front_is_unchanged(self) -> None:
        source = (100, 150, 200, 255)
        self.assertEqual(_relief_face_colour(source, "body", "front"), source)

    def test_relief_face_colour_outline_is_dark_grey(self) -> None:
        self.assertEqual(_relief_face_colour((100, 150, 200, 255), "outline", "side"), (24, 24, 24, 255))

    def test_relief_face_colour_dark_source_is_dark_grey(self) -> None:
        self.assertEqual(_relief_face_colour((70, 70, 70, 255), "body", "side"), (24, 24, 24, 255))

    def test_relief_face_colour_back_is_darkened(self) -> None:
        source = (100, 150, 200, 255)
        factor = 0.9
        expected = (int(100 * factor), int(150 * factor), int(200 * factor), 255)
        self.assertEqual(_relief_face_colour(source, "body", "back"), expected)

    def test_relief_face_colour_side_is_darkened_more(self) -> None:
        source = (100, 150, 200, 255)
        factor = 0.88
        expected = (int(100 * factor), int(150 * factor), int(200 * factor), 255)
        self.assertEqual(_relief_face_colour(source, "body", "left"), expected)

    def test_zfield_face_colour_front_is_unchanged(self) -> None:
        source = (100, 150, 200, 255)
        self.assertEqual(_zfield_face_colour(source, "body", "ellipsoid", "front"), source)

    def test_zfield_face_colour_shell_is_very_dark(self) -> None:
        source = (100, 150, 200, 255)
        factor = 0.35
        expected = (int(100 * factor), int(150 * factor), int(200 * factor), 255)
        self.assertEqual(_zfield_face_colour(source, "body", "shell", "side"), expected)

    def test_depth_multiplier_for_part(self) -> None:
        self.assertEqual(_depth_multiplier_for_part("head"), 0.8)
        self.assertEqual(_depth_multiplier_for_part("torso"), 0.55)
        self.assertEqual(_depth_multiplier_for_part("left_foot"), 1.1)
        self.assertEqual(_depth_multiplier_for_part("non_existent_part"), 0.55)


if __name__ == "__main__":
    unittest.main()
