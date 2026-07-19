"""
image.py

Image processing for the Cartridge Mosaic Generator.
"""

from collections import Counter
from models import Cell, MosaicProject
from pathlib import Path
from typing import TypeAlias

import numpy as np
from PIL import Image


CropBox: TypeAlias = tuple[int, int, int, int]


# ---------------------------------------------------------
# Data Model
# ---------------------------------------------------------


# ---------------------------------------------------------
# Coordinate Helpers
# ---------------------------------------------------------

def column_name(index: int) -> str:
    """Convert 0-based column index to Excel-style letters."""

    name = ""

    while index >= 0:
        name = chr(index % 26 + 65) + name
        index = index // 26 - 1

    return name


def coordinate(row: int, column: int) -> str:
    """Return A1 style coordinate."""

    return f"{column_name(column)}{row + 1}"


# ---------------------------------------------------------
# Image Loading
# ---------------------------------------------------------

def load_image(filename: Path) -> Image.Image:

    if not filename.exists():
        raise FileNotFoundError(filename)

    return Image.open(filename).convert("RGB")


# ---------------------------------------------------------
# Resize
# ---------------------------------------------------------

def resize_image(
    image: Image.Image,
    width: int,
    height: int,
) -> Image.Image:

    return image.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )


# ---------------------------------------------------------
# Quantize
# ---------------------------------------------------------

def quantize_image(
    image: Image.Image,
    colors: int,
    dither: bool = False,
) -> Image.Image:

    return image.quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG
        if dither
        else Image.Dither.NONE,
    )


# ---------------------------------------------------------
# Palette
# ---------------------------------------------------------

def extract_palette(
    palette_image: Image.Image,
    colors: int,
) -> dict[int, tuple[int, int, int]]:

    raw = palette_image.getpalette()

    palette = {}

    available_colors = min(colors, len(raw) // 3)

    for i in range(available_colors):

        palette[i + 1] = (

            raw[i * 3],

            raw[i * 3 + 1],

            raw[i * 3 + 2],

        )

    return palette


# ---------------------------------------------------------
# Grid Builder
# ---------------------------------------------------------

def build_grid(index_map, palette):

    grid = []

    counts = Counter()

    height = index_map.shape[0]

    width = index_map.shape[1]

    for row in range(height):

        row_cells = []

        for column in range(width):

            color = int(index_map[row, column]) + 1

            counts[color] += 1

            row_cells.append(

                Cell(

                    row=row,

                    column=column,

                    coordinate=coordinate(row, column),

                    color=color,

                    rgb=palette[color],

                )

            )

        grid.append(row_cells)

    return grid, dict(counts)


# ---------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------

def process_image(
    filename: str | Path,
    width: int,
    height: int,
    colors: int,
    dither: bool = False,
    crop_box: CropBox | None = None,
) -> MosaicProject:
    """Load and process an image while preserving the established pipeline.

    ``crop_box`` uses Pillow's left/top/right/bottom pixel coordinates.  Keeping
    crop selection at this boundary lets the editor remain independent of the
    renderer and makes project serialization straightforward later.
    """

    original = load_image(Path(filename))
    if crop_box is not None:
        left, top, right, bottom = crop_box
        if left < 0 or top < 0 or right > original.width or bottom > original.height:
            raise ValueError("Crop rectangle lies outside the source image.")
        if right <= left or bottom <= top:
            raise ValueError("Crop rectangle must have a positive size.")
        original = original.crop(crop_box)

    resized = resize_image(
        original,
        width,
        height,
    )

    palette_image = quantize_image(
        resized,
        colors,
        dither,
    )

    rgb_image = palette_image.convert("RGB")

    palette = extract_palette(
        palette_image,
        colors,
    )

    index_map = np.array(palette_image)

    grid, counts = build_grid(
        index_map,
        palette,
    )

    return MosaicProject(
        original=original,
        resized=resized,
        palette_image=palette_image,
        rgb_image=rgb_image,
        width=width,
        height=height,
        colors=len(palette),
        palette=palette,
        color_counts=counts,
        grid=grid,
    )
