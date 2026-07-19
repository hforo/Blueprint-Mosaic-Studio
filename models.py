"""
models.py

Data models used by the Cartridge Mosaic Generator.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

RGB = Tuple[int, int, int]


@dataclass(slots=True)
class Cell:
    row: int
    column: int
    coordinate: str
    color: int
    rgb: RGB


@dataclass(slots=True)
class MosaicProject:
    original: object
    resized: object
    palette_image: object
    rgb_image: object

    width: int
    height: int
    colors: int

    palette: Dict[int, RGB]
    color_counts: Dict[int, int]
    grid: List[List[Cell]]