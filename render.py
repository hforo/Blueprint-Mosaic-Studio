"""
render.py

Rendering functions for the Cartridge Mosaic Generator.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from config import (
    PROJECT_NAME,
    MASTER_BLUEPRINT,
    CELL_SIZE,
    BORDER,
    GRID_COLOR,
    GRID_LINE_WIDTH,
    HEAVY_GRID_COLOR,
    HEAVY_GRID_WIDTH,
    HEAVY_GRID_EVERY,
    TITLE_FONT_SIZE,
    HEADER_FONT_SIZE,
    CELL_FONT_SIZE,
    CARTRIDGES_PER_MODULE,
)


# ----------------------------------------------------------
# Fonts
# ----------------------------------------------------------

def load_fonts():
    """
    Attempt to load a TrueType font.
    Falls back to Pillow's default font if unavailable.
    """

    candidates = [
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
    ]

    for font_name in candidates:
        try:
            title = ImageFont.truetype(font_name, TITLE_FONT_SIZE)
            header = ImageFont.truetype(font_name, HEADER_FONT_SIZE)
            cell = ImageFont.truetype(font_name, CELL_FONT_SIZE)
            return title, header, cell
        except OSError:
            pass

    default = ImageFont.load_default()

    return default, default, default


def load_coordinate_font():
    """Load a compact font whose two-letter labels fit inside one grid cell."""
    font_size = max(8, CELL_SIZE // 2)
    for font_name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            pass
    return ImageFont.load_default()


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------

def brightness(rgb):
    r, g, b = rgb
    return (299 * r + 587 * g + 114 * b) / 1000


def text_color(rgb):
    if brightness(rgb) < 140:
        return (255, 255, 255)

    return (0, 0, 0)


def cell_position(row, column):
    """
    Returns the pixel coordinates for the upper-left corner
    of a grid cell.
    """

    x = BORDER + column * CELL_SIZE
    y = BORDER + row * CELL_SIZE

    return x, y


# ----------------------------------------------------------
# Drawing
# ----------------------------------------------------------

def draw_cell(draw, cell, font, row_offset=0, col_offset=0):
    """
    Draw one colored module.
    """

    x, y = cell_position(
        cell.row - row_offset,
        cell.column - col_offset,
    )

    draw.rectangle(
        (
            x,
            y,
            x + CELL_SIZE,
            y + CELL_SIZE,
        ),
        fill=cell.rgb,
    )

    label = str(cell.color)

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=font,
    )

    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    tx = x + (CELL_SIZE - w) / 2
    ty = y + (CELL_SIZE - h) / 2

    draw.text(
        (tx, ty),
        label,
        fill=text_color(cell.rgb),
        font=font,
    )


def draw_grid(draw, width, height):
    """
    Draw light and heavy grid lines.
    """

    total_width = width * CELL_SIZE
    total_height = height * CELL_SIZE

    # Vertical lines
    for col in range(width + 1):

        x = BORDER + col * CELL_SIZE

        if col % HEAVY_GRID_EVERY == 0:
            color = HEAVY_GRID_COLOR
            line_width = HEAVY_GRID_WIDTH
        else:
            color = GRID_COLOR
            line_width = GRID_LINE_WIDTH

        draw.line(
            (
                x,
                BORDER,
                x,
                BORDER + total_height,
            ),
            fill=color,
            width=line_width,
        )

    # Horizontal lines
    for row in range(height + 1):

        y = BORDER + row * CELL_SIZE

        if row % HEAVY_GRID_EVERY == 0:
            color = HEAVY_GRID_COLOR
            line_width = HEAVY_GRID_WIDTH
        else:
            color = GRID_COLOR
            line_width = GRID_LINE_WIDTH

        draw.line(
            (
                BORDER,
                y,
                BORDER + total_width,
                y,
            ),
            fill=color,
            width=line_width,
        )


def draw_title(draw, title_font, header_font, image_width, project):
    """
    Draw project title and project statistics.
    """

    center = BORDER + image_width // 2

    draw.text(
        (center, 15),
        PROJECT_NAME,
        anchor="ma",
        font=title_font,
        fill="black",
    )

    total_modules = project.width * project.height
    total_cartridges = total_modules * CARTRIDGES_PER_MODULE
    finished_width = project.finished_width_inches
    finished_height = project.finished_height_inches
    stats = (
        f"{total_modules:,} Modules   |   "
        f"{total_cartridges:,} Cartridges   |   "
        f"{finished_width:.1f}\" × {finished_height:.1f}\""
    )

    draw.text(
        (center, 50),
        stats,
        anchor="ma",
        font=header_font,
        fill="black",
    )


def draw_row_labels(draw, font, height, row_offset=0):
    """
    Draw row numbers.
    """

    for row in range(height):

        y = BORDER + row * CELL_SIZE + CELL_SIZE / 2

        draw.text(
            (BORDER - 12, y),
            str(row + row_offset + 1),
            anchor="rm",
            font=font,
            fill="black",
        )


def excel_column_name(index):
    """
    Convert 0-based column index into Excel letters.
    """

    result = ""

    while index >= 0:
        result = chr(index % 26 + 65) + result
        index = index // 26 - 1

    return result


def draw_column_labels(draw, font, width, col_offset=0):
    """
    Draw column letters.
    """

    for col in range(width):

        x = BORDER + col * CELL_SIZE + CELL_SIZE / 2

        draw.text(
            (x, BORDER - 4),
            excel_column_name(col + col_offset),
            anchor="ms",
            font=font,
            fill="black",
        )

        # ----------------------------------------------------------
# Main Renderer
# ----------------------------------------------------------


def blueprint_output_path(project) -> Path:
    """Return a descriptive output path for a generated master blueprint."""
    color_count = len(project.palette)
    source_stem = (
        project.source_path.stem
        if project.source_path is not None
        else "image"
    )
    safe_source_stem = "".join(
        "_" if character in '<>:"/\\|?*' else character
        for character in source_stem
    ).strip(" .") or "image"
    filename = (
        f"{MASTER_BLUEPRINT.stem}_{safe_source_stem}_{color_count}colors_"
        f"{project.width}x{project.height}{MASTER_BLUEPRINT.suffix}"
    )
    return MASTER_BLUEPRINT.with_name(filename)


def render_master(project):
    """
    Render the complete master blueprint.

    Parameters
    ----------
    data : dict
        Dictionary returned from image.process_image()
    """

    width = project.width
    height = project.height
    grid = project.grid

    image_width = width * CELL_SIZE
    image_height = height * CELL_SIZE

    canvas = Image.new(
        "RGB",
        (
            image_width + BORDER * 2,
            image_height + BORDER * 2,
        ),
        "white",
    )

    draw = ImageDraw.Draw(canvas)

    title_font, header_font, cell_font = load_fonts()
    coordinate_font = load_coordinate_font()

    # ------------------------------------------------------
    # Title
    # ------------------------------------------------------

    draw_title(
        draw,
        title_font,
        header_font,
        image_width,
        project,
    )

    # ------------------------------------------------------
    # Cells
    # ------------------------------------------------------

    for row in grid:
        for cell in row:
            draw_cell(
                draw,
                cell,
                cell_font,
            )

    # ------------------------------------------------------
    # Grid
    # ------------------------------------------------------

    draw_grid(
        draw,
        width,
        height,
    )

    # ------------------------------------------------------
    # Labels
    # ------------------------------------------------------

    draw_row_labels(
        draw,
        header_font,
        height,
    )

    draw_column_labels(
        draw,
        coordinate_font,
        width,
    )

    # ------------------------------------------------------
    # Footer
    # ------------------------------------------------------

    footer = (
        f"{PROJECT_NAME}   •   "
        f"{width} × {height} modules   •   "
        f"{len(project.palette)} palette colors"
    )

    draw.text(
        (
            BORDER,
            image_height + BORDER + 25,
        ),
        footer,
        font=header_font,
        fill="black",
    )

    # ------------------------------------------------------
    # Save
    # ------------------------------------------------------

    output_path = blueprint_output_path(project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)

    print()
    print("=" * 60)
    print("Blueprint created successfully!")
    print(f"Saved to: {output_path}")
    print(f"Image size: {canvas.width:,} x {canvas.height:,} pixels")
    print("=" * 60)
    print()

    return canvas
