"""
render.py

Rendering functions for Blueprint Mosaic Studio.
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
)


MOSAIC_BACKGROUNDS = {
    "White": (255, 255, 255),
    "Black": (24, 24, 24),
    "Neutral gray": (150, 150, 150),
    "Maple plywood": (214, 181, 126),
}


def mosaic_background_rgb(name):
    return MOSAIC_BACKGROUNDS.get(name, MOSAIC_BACKGROUNDS["White"])


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


def load_sized_font(font_size):
    """Load a readable sans-serif font at an explicit pixel size."""
    for font_name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            pass
    return ImageFont.load_default()


def load_coordinate_font(cell_size=CELL_SIZE):
    """Load a compact font whose two-letter labels fit inside one grid cell."""
    return load_sized_font(max(8, cell_size // 2))


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


def cell_position(row, column, cell_size=CELL_SIZE, border=BORDER):
    """
    Returns the pixel coordinates for the upper-left corner
    of a grid cell.
    """

    x = border + column * cell_size
    y = border + row * cell_size

    return x, y


# ----------------------------------------------------------
# Drawing
# ----------------------------------------------------------

def draw_tile_fill(draw, x, y, size, fill_rgb, tile_type):
    """Draw the physical-piece silhouette within one logical grid cell."""
    if tile_type in ("Round disc — one face", "Sphere — all surface"):
        inset = max(1, round(size * 0.06))
        draw.ellipse(
            (x + inset, y + inset, x + size - inset, y + size - inset),
            fill=fill_rgb,
        )
    elif tile_type == "4-piece 5.56 cartridge tile" and size >= 4:
        half = size / 2
        # Keep the four cartridge ends almost tangent. At thumbnail scale they
        # touch; larger renders retain only a hairline of visible backing.
        inset = max(0, round(size * 0.01))
        for tile_row in range(2):
            for tile_column in range(2):
                draw.ellipse(
                    (
                        x + tile_column * half + inset,
                        y + tile_row * half + inset,
                        x + (tile_column + 1) * half - inset,
                        y + (tile_row + 1) * half - inset,
                    ),
                    fill=fill_rgb,
                )
    else:
        draw.rectangle((x, y, x + size, y + size), fill=fill_rgb)

def draw_cell(
    draw,
    cell,
    font,
    row_offset=0,
    col_offset=0,
    fill_rgb=None,
    show_label=True,
    cell_size=CELL_SIZE,
    border=BORDER,
    tile_type="Flat square — one face",
):
    """
    Draw one colored mosaic tile.
    """

    x, y = cell_position(
        cell.row - row_offset,
        cell.column - col_offset,
        cell_size,
        border,
    )

    display_rgb = fill_rgb if fill_rgb is not None else cell.rgb
    draw_tile_fill(draw, x, y, cell_size, display_rgb, tile_type)

    if not show_label:
        return

    label = str(cell.color)

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=font,
    )

    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    tx = x + (cell_size - w) / 2
    ty = y + (cell_size - h) / 2

    draw.text(
        (tx, ty),
        label,
        fill=text_color(display_rgb),
        font=font,
    )


def draw_grid(draw, width, height, cell_size=CELL_SIZE, border=BORDER):
    """
    Draw light and heavy grid lines.
    """

    total_width = width * cell_size
    total_height = height * cell_size

    # Vertical lines
    for col in range(width + 1):

        x = border + col * cell_size

        if col % HEAVY_GRID_EVERY == 0:
            color = HEAVY_GRID_COLOR
            line_width = HEAVY_GRID_WIDTH
        else:
            color = GRID_COLOR
            line_width = GRID_LINE_WIDTH

        draw.line(
            (
                x,
                border,
                x,
                border + total_height,
            ),
            fill=color,
            width=line_width,
        )

    # Horizontal lines
    for row in range(height + 1):

        y = border + row * cell_size

        if row % HEAVY_GRID_EVERY == 0:
            color = HEAVY_GRID_COLOR
            line_width = HEAVY_GRID_WIDTH
        else:
            color = GRID_COLOR
            line_width = GRID_LINE_WIDTH

        draw.line(
            (
                border,
                y,
                border + total_width,
                y,
            ),
            fill=color,
            width=line_width,
        )


def draw_title(
    draw,
    title_font,
    header_font,
    image_width,
    project,
    title_suffix=None,
):
    """
    Draw project title and project statistics.
    """

    center = BORDER + image_width // 2

    title = PROJECT_NAME
    if title_suffix:
        title = f"{title} — {title_suffix}"
    draw.text(
        (center, 15),
        title,
        anchor="ma",
        font=title_font,
        fill="black",
    )

    total_tiles = project.width * project.height
    finished_width = project.finished_width_inches
    finished_height = project.finished_height_inches
    stats = (
        f"{total_tiles:,} Tiles   |   "
        f"{finished_width:.1f}\" × {finished_height:.1f}\""
    )

    draw.text(
        (center, 50),
        stats,
        anchor="ma",
        font=header_font,
        fill="black",
    )


def draw_row_labels(
    draw, font, height, row_offset=0, cell_size=CELL_SIZE, border=BORDER,
):
    """
    Draw row numbers.
    """

    for row in range(height):

        y = border + row * cell_size + cell_size / 2

        draw.text(
            (border - 12, y),
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


def draw_column_labels(
    draw, font, width, col_offset=0, cell_size=CELL_SIZE, border=BORDER,
):
    """
    Draw column letters.
    """

    for col in range(width):

        x = border + col * cell_size + cell_size / 2

        draw.text(
            (x, border - 4),
            excel_column_name(col + col_offset),
            anchor="ms",
            font=font,
            fill="black",
        )

        # ----------------------------------------------------------
# Main Renderer
# ----------------------------------------------------------


def blueprint_output_path(
    project,
    color_count=None,
    filename_tag=None,
) -> Path:
    """Return a descriptive output path for a generated master blueprint."""
    if color_count is None:
        color_count = len(set(project.palette.values()))
    source_stem = (
        project.source_path.stem
        if project.source_path is not None
        else "image"
    )
    safe_source_stem = "".join(
        "_" if character in '<>:"/\\|?*' else character
        for character in source_stem
    ).strip(" .") or "image"
    safe_tag = ""
    if filename_tag:
        cleaned_tag = "".join(
            "_" if character in '<>:"/\\|?*' else character
            for character in filename_tag
        ).strip(" .")
        if cleaned_tag:
            safe_tag = f"_{cleaned_tag}"
    filename = (
        f"{MASTER_BLUEPRINT.stem}_{safe_source_stem}{safe_tag}_"
        f"{color_count}colors_"
        f"{project.width}x{project.height}{MASTER_BLUEPRINT.suffix}"
    )
    return MASTER_BLUEPRINT.with_name(filename)


def render_master(
    project,
    color_overrides=None,
    filename_tag=None,
    palette_color_count=None,
    title_suffix=None,
    show_labels=True,
    show_annotations=True,
):
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

    if show_annotations:
        draw_title(
            draw,
            title_font,
            header_font,
            image_width,
            project,
            title_suffix=title_suffix,
        )

    # ------------------------------------------------------
    # Cells
    # ------------------------------------------------------

    draw.rectangle(
        (BORDER, BORDER, BORDER + image_width, BORDER + image_height),
        fill=mosaic_background_rgb(project.background_name),
    )

    for row in grid:
        for cell in row:
            draw_cell(
                draw,
                cell,
                cell_font,
                fill_rgb=(
                    color_overrides.get(cell.color)
                    if color_overrides is not None
                    else None
                ),
                show_label=show_labels,
                tile_type=project.tile_type,
            )

    # ------------------------------------------------------
    # Grid
    # ------------------------------------------------------

    draw_grid(
        draw,
        width,
        height,
    )
    draw.rectangle(
        (BORDER, BORDER, BORDER + image_width, BORDER + image_height),
        outline="black",
        width=max(2, GRID_LINE_WIDTH),
    )

    # ------------------------------------------------------
    # Labels
    # ------------------------------------------------------

    if show_labels:
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

    display_color_count = (
        palette_color_count
        if palette_color_count is not None
        else len(set(project.palette.values()))
    )
    footer_name = PROJECT_NAME
    if title_suffix:
        footer_name = f"{footer_name} — {title_suffix}"
    footer = (
        f"{footer_name}   •   "
        f"{width} × {height} modules   •   "
        f"{display_color_count} palette colors"
    )

    if show_annotations:
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

    output_path = blueprint_output_path(
        project,
        color_count=display_color_count,
        filename_tag=filename_tag,
    )
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
