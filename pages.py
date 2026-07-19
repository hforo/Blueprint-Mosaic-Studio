"""Generate printable mosaic pages."""

from math import ceil

from PIL import Image, ImageDraw

from config import (
    BORDER,
    CELL_SIZE,
    PAGE_COLUMNS,
    PAGE_ROWS,
    PAGES_FOLDER,
    PROJECT_NAME,
)
from render import (
    draw_cell,
    draw_column_labels,
    draw_grid,
    draw_row_labels,
    load_fonts,
)


def render_pages(project) -> None:
    """Render the project's grid as a set of printable PNG pages."""
    PAGES_FOLDER.mkdir(exist_ok=True)
    title_font, header_font, cell_font = load_fonts()
    page_columns = ceil(project.width / PAGE_COLUMNS)
    page_rows = ceil(project.height / PAGE_ROWS)
    total_pages = page_columns * page_rows
    page_number = 1

    for page_row in range(page_rows):
        for page_column in range(page_columns):
            start_row = page_row * PAGE_ROWS
            start_column = page_column * PAGE_COLUMNS
            end_row = min(start_row + PAGE_ROWS, project.height)
            end_column = min(start_column + PAGE_COLUMNS, project.width)
            width = end_column - start_column
            height = end_row - start_row
            canvas = Image.new(
                "RGB",
                (
                    width * CELL_SIZE + BORDER * 2,
                    height * CELL_SIZE + BORDER * 2,
                ),
                "white",
            )
            draw = ImageDraw.Draw(canvas)
            draw.text(
                (BORDER, 20),
                f"{PROJECT_NAME}  Page {page_number} of {total_pages}",
                font=title_font,
                fill="black",
            )
            draw.text(
                (BORDER, 50),
                (
                    f"Columns {start_column + 1}-{end_column}   "
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
                    )
            draw_grid(draw, width, height)
            draw_row_labels(draw, header_font, height)
            draw_column_labels(draw, header_font, width)
            canvas.save(
                PAGES_FOLDER / f"Page_{page_number:02}.png",
                optimize=True,
            )
            page_number += 1
