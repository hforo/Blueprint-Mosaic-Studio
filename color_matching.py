"""Perceptual matching against the bundled Sherwin-Williams color catalog."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path


RGB = tuple[int, int, int]
Lab = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class PaintColor:
    """A named paint color and its display-space representation."""

    code: str
    name: str
    rgb: RGB
    hex_value: str
    lab: Lab

    @property
    def display_code(self) -> str:
        return f"SW {self.code.removeprefix('SW')}"


@dataclass(frozen=True, slots=True)
class PaintMatch:
    """Nearest catalog color and its CIE76 perceptual distance."""

    color: PaintColor
    delta_e: float


class SherwinWilliamsMatcher:
    """Offline nearest-color lookup for the official ColorSnap catalog."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        if catalog_path is None:
            catalog_path = (
                Path(__file__).resolve().parent
                / "data"
                / "sherwin_williams.json"
            )
        self.catalog_path = catalog_path
        self.source = ""
        self._colors = self._load_catalog(catalog_path)
        self._cache: dict[RGB, PaintMatch] = {}

    @property
    def color_count(self) -> int:
        return len(self._colors)

    def nearest(self, rgb: RGB) -> PaintMatch:
        """Return the catalog entry with the smallest CIE76 distance."""
        if rgb in self._cache:
            return self._cache[rgb]
        target = rgb_to_lab(rgb)
        color, distance = min(
            (
                (color, delta_e_cie76(target, color.lab))
                for color in self._colors
            ),
            key=lambda result: result[1],
        )
        match = PaintMatch(color, distance)
        self._cache[rgb] = match
        return match

    def _load_catalog(self, path: Path) -> tuple[PaintColor, ...]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load paint catalog: {path}") from error
        self.source = str(payload.get("source", ""))
        colors = []
        for record in payload.get("colors", []):
            rgb = tuple(int(channel) for channel in record["rgb"])
            if len(rgb) != 3 or any(channel < 0 or channel > 255 for channel in rgb):
                raise ValueError(f"Invalid RGB value in paint catalog: {rgb}")
            typed_rgb: RGB = (rgb[0], rgb[1], rgb[2])
            colors.append(
                PaintColor(
                    code=str(record["code"]),
                    name=str(record["name"]),
                    rgb=typed_rgb,
                    hex_value=str(record["hex"]),
                    lab=rgb_to_lab(typed_rgb),
                )
            )
        if not colors:
            raise ValueError(f"Paint catalog contains no colors: {path}")
        return tuple(colors)


def rgb_to_lab(rgb: RGB) -> Lab:
    """Convert an sRGB color to CIE L*a*b* using a D65 reference white."""
    linear = []
    for channel in rgb:
        value = channel / 255.0
        linear.append(
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = linear
    x = (red * 0.4124564 + green * 0.3575761 + blue * 0.1804375) / 0.95047
    y = red * 0.2126729 + green * 0.7151522 + blue * 0.0721750
    z = (red * 0.0193339 + green * 0.1191920 + blue * 0.9503041) / 1.08883

    def pivot(value: float) -> float:
        epsilon = 216 / 24389
        kappa = 24389 / 27
        return value ** (1 / 3) if value > epsilon else (kappa * value + 16) / 116

    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e_cie76(first: Lab, second: Lab) -> float:
    """Calculate straight-line perceptual distance in CIE L*a*b* space."""
    return sqrt(sum((left - right) ** 2 for left, right in zip(first, second)))
