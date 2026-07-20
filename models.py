"""
models.py

Data models used by Blueprint Mosaic Studio.
"""

from dataclasses import dataclass
from pathlib import Path
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
    source_path: Path | None = None
    tile_size_inches: float = 0.75
    tile_type: str = "Flat square — one face"

    @property
    def finished_width_inches(self) -> float:
        return self.width * self.tile_size_inches

    @property
    def finished_height_inches(self) -> float:
        return self.height * self.tile_size_inches
