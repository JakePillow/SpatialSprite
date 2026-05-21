from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the tool and tools directories to the path to allow imports
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
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


def approx_equal(value: list[float]) -> pytest.approx:
    """Helper for comparing lists of floats."""
    return pytest.approx(value, abs=1e-6)


# === Test _rgba_float ===
def test_rgba_float_converts_correctly():
    assert _rgba_float((255, 128, 0, 255)) == approx_equal([1.0, 128 / 255.0, 0.0, 1.0])
    assert _rgba_float((0, 0, 0, 0)) == approx_equal([0.0, 0.0, 0.0, 0.0])


# === Test _vibrant_side_colour ===
# NOTE: These tests are written against the *intended* logic, which is to darken
# side faces. The current implementation in the file has a bug where it does not
# darken the colors. These tests will fail until that bug is fixed, demonstrating
# the value of unit testing for preventing regressions.
def test_vibrant_side_colour_darkens_bright_colours():
    """A bright color should be significantly darkened."""
    bright_red = (200, 50, 50, 255)
    # Correct logic uses a factor of 0.75 for bright colors (max component > 48)
    factor = 0.75
    expected = [(200 * factor) / 255.0, (50 * factor) / 255.0, (50 * factor) / 255.0, 1.0]
    assert _vibrant_side_colour(bright_red) == approx_equal(expected)


def test_vibrant_side_colour_applies_less_darkening_for_dark_colours():
    """A dark color should be only slightly darkened to preserve detail."""
    dark_blue = (40, 40, 48, 255)
    # Correct logic uses a factor of 0.9 for dark colors (max component <= 48)
    factor = 0.9
    expected = [(40 * factor) / 255.0, (40 * factor) / 255.0, (48 * factor) / 255.0, 1.0]
    assert _vibrant_side_colour(dark_blue) == approx_equal(expected)


def test_vibrant_side_colour_handles_black():
    """Black should remain black (or very close to it)."""
    black = (0, 0, 0, 255)
    factor = 0.9
    expected = [0.0, 0.0, 0.0, 1.0]
    assert _vibrant_side_colour(black) == approx_equal(expected)


# === Test _relief_face_colour ===
def test_relief_face_colour_front_is_unchanged():
    source = (100, 150, 200, 255)
    assert _relief_face_colour(source, "body", "front") == source


def test_relief_face_colour_outline_is_dark_grey():
    source = (100, 150, 200, 255)
    expected = (24, 24, 24, 255)
    assert _relief_face_colour(source, "outline", "side") == expected


def test_relief_face_colour_dark_source_is_dark_grey():
    source = (70, 70, 70, 255)
    expected = (24, 24, 24, 255)
    assert _relief_face_colour(source, "body", "side") == expected


def test_relief_face_colour_back_is_darkened():
    source = (100, 150, 200, 255)
    factor = 0.9
    expected = (int(100 * factor), int(150 * factor), int(200 * factor), 255)
    assert _relief_face_colour(source, "body", "back") == expected


def test_relief_face_colour_side_is_darkened_more():
    source = (100, 150, 200, 255)
    factor = 0.88
    expected = (int(100 * factor), int(150 * factor), int(200 * factor), 255)
    assert _relief_face_colour(source, "body", "left") == expected


# === Test _zfield_face_colour ===
def test_zfield_face_colour_front_is_unchanged():
    source = (100, 150, 200, 255)
    assert _zfield_face_colour(source, "body", "ellipsoid", "front") == source


def test_zfield_face_colour_shell_is_very_dark():
    source = (100, 150, 200, 255)
    factor = 0.35
    expected = (int(100 * factor), int(150 * factor), int(200 * factor), 255)
    assert _zfield_face_colour(source, "body", "shell", "side") == expected


# === Test _depth_multiplier_for_part ===
def test_depth_multiplier_for_part():
    assert _depth_multiplier_for_part("head") == 0.8
    assert _depth_multiplier_for_part("torso") == 0.55
    assert _depth_multiplier_for_part("left_foot") == 1.1
    assert _depth_multiplier_for_part("non_existent_part") == 0.55  # falls back to default
