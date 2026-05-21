from __future__ import annotations

import sys
import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
TOOLS_ROOT = WORKSPACE_ROOT / "tools"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from build_topological_sprite_model import (  # noqa: E402
    _depth_multiplier_for_part,
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
