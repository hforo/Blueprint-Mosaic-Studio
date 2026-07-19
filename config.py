"""
config.py

Global configuration for the Cartridge Mosaic Generator.
"""

from pathlib import Path

# Printable page settings

PAGE_COLUMNS = 24
PAGE_ROWS = 20

PAGE_MARGIN = 100
PAGE_CELL_SIZE = 40

PAGE_TITLE_HEIGHT = 80

TOTAL_PAGE_COLUMNS = (GRID_WIDTH + PAGE_COLUMNS - 1) // PAGE_COLUMNS
TOTAL_PAGE_ROWS = (GRID_HEIGHT + PAGE_ROWS - 1) // PAGE_ROWS

TOTAL_PAGES = TOTAL_PAGE_COLUMNS * TOTAL_PAGE_ROWS
# ------------------------------------------------------------
# Project
# ------------------------------------------------------------

PROJECT_NAME = "White Dove"

# ------------------------------------------------------------
# Input Image
# ------------------------------------------------------------

IMAGE_FILE = Path("images/dove.png")

# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

MASTER_BLUEPRINT = OUTPUT_FOLDER / "Master_Blueprint.png"
COORDINATE_CSV = OUTPUT_FOLDER / "Coordinates.csv"
EXCEL_FILE = OUTPUT_FOLDER / "Blueprint.xlsx"
STATISTICS_FILE = OUTPUT_FOLDER / "Statistics.txt"

# ------------------------------------------------------------
# Mosaic Settings
# ------------------------------------------------------------

GRID_WIDTH = 96
GRID_HEIGHT = 80

NUMBER_OF_COLORS = 64

MODULE_SIZE_INCHES = 0.75
CARTRIDGES_PER_MODULE = 4

# ------------------------------------------------------------
# Rendering
# ------------------------------------------------------------

CELL_SIZE = 20
BORDER = 80

GRID_COLOR = (180, 180, 180)
HEAVY_GRID_COLOR = (0, 0, 0)

GRID_LINE_WIDTH = 1
HEAVY_GRID_WIDTH = 3

HEAVY_GRID_EVERY = 4

# ------------------------------------------------------------
# Fonts
# ------------------------------------------------------------

TITLE_FONT_SIZE = 30
HEADER_FONT_SIZE = 18
CELL_FONT_SIZE = 12

# ------------------------------------------------------------
# Derived Values
# ------------------------------------------------------------

TOTAL_MODULES = GRID_WIDTH * GRID_HEIGHT

TOTAL_CARTRIDGES = (
    TOTAL_MODULES *
    CARTRIDGES_PER_MODULE
)

FINISHED_WIDTH = GRID_WIDTH * MODULE_SIZE_INCHES

FINISHED_HEIGHT = GRID_HEIGHT * MODULE_SIZE_INCHES