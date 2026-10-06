from __future__ import annotations

from orchestra.app import THEME
from orchestra.palette import ORCH_SHADES, STATUS_COLORS


def rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def spread(hex_color: str) -> int:
    red, green, blue = rgb(hex_color)
    return max(red, green, blue) - min(red, green, blue)


def test_theme_core_colors_are_grayscale():
    for attribute in ("primary", "secondary", "accent", "foreground", "background", "surface", "panel", "boost"):
        color = getattr(THEME, attribute)
        assert color is not None
        assert spread(color) <= 16, f"{attribute}={color} should be gray"


def test_orchestrator_shades_are_grayscale():
    for color in ORCH_SHADES:
        assert spread(color) <= 16, f"{color} should be gray"


def test_status_colors_stay_muted():
    for name, color in STATUS_COLORS.items():
        assert spread(color) <= 64, f"{name}={color} is too saturated for the grayscale theme"
