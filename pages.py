"""Generate printable mosaic pages and page-navigation metadata."""

from dataclasses import dataclass
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from config import (
    BORDER,
    CELL_SIZE,
    PAGE_CELL_SIZE,
    PAGE_COLUMNS,
    PAGE_ROWS,
    PAGE_TITLE_HEIGHT,
    PAGES_FOLDER,
    PROJECT_NAME,
)
from render import (
    draw_cell,
    draw_column_labels,
    draw_grid,
    draw_row_labels,
    draw_tile_fill,
    load_coordinate_font,
    load_fonts,
    load_sized_font,
    mosaic_background_rgb,
)


OVERVIEW_SIZE = (240, 180)
PAGE_SIDEBAR_WIDTH = 290


@dataclass(frozen=True, slots=True)
class PageSection:
    """A printable section and its location within the complete mosaic."""

    page_number: int
    total_pages: int
    start_row: int
    end_row: int
    start_column: int
    end_column: int
    image_path: Path
    thumbnail_path: Path

    @property
    def title(self) -> str:
        return f"Page {self.page_number} of {self.total_pages}"

    @property
    def location_text(self) -> str:
        return (
            f"Columns {self.start_column + 1}–{self.end_column} · "
            f"Rows {self.start_row + 1}–{self.end_row}"
        )


def render_pages(
    project,
    color_overrides=None,
    color_label: str | None = None,
    label_overrides=None,
) -> list[PageSection]:
    """Render printable pages with a full-mosaic location overview."""
    PAGES_FOLDER.mkdir(exist_ok=True)
    thumbnails_folder = PAGES_FOLDER / "Thumbnails"
    thumbnails_folder.mkdir(exist_ok=True)
    title_font, header_font, _ = load_fonts()
    cell_font = load_sized_font(max(14, PAGE_CELL_SIZE // 3))
    coordinate_font = load_coordinate_font(PAGE_CELL_SIZE)
    page_columns = ceil(project.width / PAGE_COLUMNS)
    page_rows = ceil(project.height / PAGE_ROWS)
    total_pages = page_columns * page_rows
    page_number = 1
    sections: list[PageSection] = []

    for page_row in range(page_rows):
        for page_column in range(page_columns):
            start_row = page_row * PAGE_ROWS
            start_column = page_column * PAGE_COLUMNS
            end_row = min(start_row + PAGE_ROWS, project.height)
            end_column = min(start_column + PAGE_COLUMNS, project.width)
            width = end_column - start_column
            height = end_row - start_row
            page_border = PAGE_TITLE_HEIGHT
            grid_width = width * PAGE_CELL_SIZE + page_border * 2
            canvas = Image.new(
                "RGB",
                (
                    grid_width + PAGE_SIDEBAR_WIDTH,
                    height * PAGE_CELL_SIZE + page_border * 2,
                ),
                "white",
            )
            draw = ImageDraw.Draw(canvas)
            draw.rectangle(
                (
                    page_border,
                    page_border,
                    page_border + width * PAGE_CELL_SIZE,
                    page_border + height * PAGE_CELL_SIZE,
                ),
                fill=mosaic_background_rgb(project.background_name),
            )
            page_title = (
                project.source_path.name
                if project.source_path is not None
                else PROJECT_NAME
            )
            if color_label:
                page_title = f"{page_title} — {color_label}"
            draw.text(
                (BORDER, 20),
                page_title,
                font=title_font,
                fill="black",
            )
            draw.text(
                (BORDER, 60),
                (
                    f"Page {page_number} of {total_pages}   ·   "
                    f"Columns {start_column + 1}-{end_column}   ·   "
                    f"Rows {start_row + 1}-{end_row}"
                ),
                font=header_font,
                fill="black",
            )
            for row in range(start_row, end_row):
                for column in range(start_column, end_column):
                    draw_cell(
                        draw,
                        project.grid[row][column],
                        cell_font,
                        row_offset=start_row,
                        col_offset=start_column,
                        fill_rgb=(
                            color_overrides.get(project.grid[row][column].color)
                            if color_overrides is not None
                            else None
                        ),
                        cell_size=PAGE_CELL_SIZE,
                        border=page_border,
                        tile_type=project.tile_type,
                        label_number=(
                            label_overrides.get(project.grid[row][column].color)
                            if label_overrides is not None else None
                        ),
                    )
            draw_grid(
                draw, width, height,
                cell_size=PAGE_CELL_SIZE, border=page_border,
            )
            draw.rectangle(
                (
                    page_border,
                    page_border,
                    page_border + width * PAGE_CELL_SIZE,
                    page_border + height * PAGE_CELL_SIZE,
                ),
                outline="black",
                width=2,
            )
            draw_row_labels(
                draw,
                cell_font,
                height,
                row_offset=start_row,
                cell_size=PAGE_CELL_SIZE,
                border=page_border,
            )
            draw_column_labels(
                draw,
                coordinate_font,
                width,
                col_offset=start_column,
                cell_size=PAGE_CELL_SIZE,
                border=page_border,
            )

            overview = render_location_thumbnail(
                project,
                start_row,
                end_row,
                start_column,
                end_column,
                color_overrides=color_overrides,
            )
            panel_x = grid_width + 24
            draw.text(
                (panel_x, 22),
                "Location in mosaic",
                font=header_font,
                fill="black",
            )
            canvas.paste(overview, (panel_x, 62))
            draw.rectangle(
                (
                    panel_x - 1,
                    61,
                    panel_x + overview.width,
                    62 + overview.height,
                ),
                outline=(120, 120, 120),
                width=1,
            )
            draw.text(
                (panel_x, 78 + overview.height),
                f"Page {page_number}\n"
                f"Columns {start_column + 1}–{end_column}\n"
                f"Rows {start_row + 1}–{end_row}",
                font=cell_font,
                fill="black",
                spacing=5,
            )

            image_path = PAGES_FOLDER / f"Page_{page_number:02}.png"
            thumbnail_path = thumbnails_folder / f"Page_{page_number:02}.png"
            canvas.save(image_path, optimize=True)
            overview.save(thumbnail_path, optimize=True)
            sections.append(
                PageSection(
                    page_number=page_number,
                    total_pages=total_pages,
                    start_row=start_row,
                    end_row=end_row,
                    start_column=start_column,
                    end_column=end_column,
                    image_path=image_path.resolve(),
                    thumbnail_path=thumbnail_path.resolve(),
                )
            )
            page_number += 1

    return sections


def render_location_thumbnail(
    project,
    start_row: int,
    end_row: int,
    start_column: int,
    end_column: int,
    color_overrides=None,
) -> Image.Image:
    """Render the whole mosaic with the current page outlined and shaded."""
    if color_overrides is None:
        source = project.rgb_image.convert("RGB")
    else:
        source = Image.new("RGB", (project.width, project.height))
        source.putdata(
            [
                color_overrides.get(cell.color, cell.rgb)
                for row in project.grid
                for cell in row
            ]
        )
    shaped_tiles = project.tile_type in (
        "Round disc — one face",
        "Sphere — all surface",
        "4-piece 5.56 cartridge tile",
    )
    if shaped_tiles:
        # Render generously before reduction so circular silhouettes and the
        # gaps between four-piece groups survive overview-thumbnail scaling.
        shape_scale = 12
        shaped_source = Image.new(
            "RGB",
            (project.width * shape_scale, project.height * shape_scale),
            mosaic_background_rgb(project.background_name),
        )
        shaped_draw = ImageDraw.Draw(shaped_source)
        for row in project.grid:
            for cell in row:
                fill_rgb = (
                    color_overrides.get(cell.color, cell.rgb)
                    if color_overrides is not None else cell.rgb
                )
                draw_tile_fill(
                    shaped_draw,
                    cell.column * shape_scale,
                    cell.row * shape_scale,
                    shape_scale,
                    fill_rgb,
                    project.tile_type,
                )
        source = shaped_source
    contained = ImageOps.contain(
        source,
        OVERVIEW_SIZE,
        Image.Resampling.LANCZOS if shaped_tiles else Image.Resampling.NEAREST,
    )
    overview = Image.new("RGB", OVERVIEW_SIZE, (235, 235, 235))
    offset_x = (OVERVIEW_SIZE[0] - contained.width) // 2
    offset_y = (OVERVIEW_SIZE[1] - contained.height) // 2
    overview.paste(contained, (offset_x, offset_y))
    overview_draw = ImageDraw.Draw(overview)
    overview_draw.rectangle(
        (
            offset_x,
            offset_y,
            offset_x + contained.width - 1,
            offset_y + contained.height - 1,
        ),
        outline="black",
        width=1,
    )

    scale_x = contained.width / project.width
    scale_y = contained.height / project.height
    rectangle = (
        round(offset_x + start_column * scale_x),
        round(offset_y + start_row * scale_y),
        round(offset_x + end_column * scale_x) - 1,
        round(offset_y + end_row * scale_y) - 1,
    )
    draw = ImageDraw.Draw(overview, "RGBA")
    draw.rectangle(rectangle, fill=(255, 40, 40, 55))
    draw.rectangle(rectangle, outline=(220, 0, 0, 255), width=3)
    return overview
