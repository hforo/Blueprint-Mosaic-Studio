"""Offline exports for generated blueprint packages and shopping lists."""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from paint_estimation import container_plan_text


PRINT_DPI = 150
LETTER_PORTRAIT = (1275, 1650)
LETTER_LANDSCAPE = (1650, 1275)


def export_shopping_csv(path: str | Path, plan) -> None:
    with Path(path).open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow([
            "Catalog", "Color code", "Color name", "Hex", "Tiles",
            "Estimated mL", "Estimated fl oz", "Suggested containers",
            "Estimated proportional cost",
        ])
        for row in plan.rows:
            writer.writerow([
                plan.catalog_name, row.paint.display_code, row.paint.name,
                row.paint.hex_value, row.tile_count,
                f"{row.estimate.milliliters:.1f}",
                f"{row.estimate.fluid_ounces:.2f}",
                container_plan_text(row.estimate.fluid_ounces),
                f"{row.estimated_cost:.2f}",
            ])


def _summary_page(
    plan, source_name: str, rows, page_number: int, total_pages: int,
    project=None,
) -> Image.Image:
    width, height = LETTER_PORTRAIT
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=30)
    body = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=15)
    draw.text(
        (55, 45),
        f"{source_name} — Supplies & Cost ({page_number}/{total_pages})",
        fill="black", font=title,
    )
    details = (
        f"Catalog: {plan.catalog_name}   |   "
        f"Total estimated cost: ${plan.total_estimated_cost:,.2f}"
    )
    if project is not None:
        details += (
            f"\n{project.width} × {project.height} grid   |   "
            f"{project.width * project.height:,} tiles   |   "
            f"{project.tile_type}"
        )
    draw.multiline_text((55, 95), details, fill="black", font=body, spacing=6)

    y = 165
    draw.rectangle((50, y, width - 50, y + 34), fill=(225, 225, 225))
    for x, label in (
        (60, "COLOR / NAME"), (600, "TILES"), (690, "PAINT NEEDED"),
        (875, "BUY"), (1120, "COST"),
    ):
        draw.text((x, y + 7), label, fill="black", font=small)
    y += 42

    for row in rows:
        draw.rectangle((55, y, 87, y + 32), fill=row.paint.rgb, outline="black")
        draw.text(
            (98, y + 5), f"{row.paint.display_code}  {row.paint.name}",
            fill="black", font=small,
        )
        draw.text((610, y + 5), f"{row.tile_count:,}", fill="black", font=small)
        draw.text(
            (690, y + 5),
            f"{row.estimate.milliliters:.0f} mL / "
            f"{row.estimate.fluid_ounces:.2f} oz",
            fill="black", font=small,
        )
        draw.text(
            (875, y + 5), container_plan_text(row.estimate.fluid_ounces),
            fill="black", font=small,
        )
        draw.text(
            (1120, y + 5), f"${row.estimated_cost:,.2f}",
            fill="black", font=small,
        )
        draw.line(
            (50, y + 37, width - 50, y + 37),
            fill=(215, 215, 215), width=1,
        )
        y += 42

    draw.text(
        (55, height - 82),
        "Container suggestions assume standard 8 fl oz samples, 32 fl oz "
        "quarts, and 128 fl oz gallons; verify manufacturer availability.",
        fill=(80, 80, 80), font=small,
    )
    draw.text(
        (55, height - 57),
        "Costs are proportional estimates at the configured gallon price and "
        "do not represent minimum retail purchase cost.",
        fill=(80, 80, 80), font=small,
    )
    return image


def _printable_image_page(source: Image.Image, title_text: str) -> Image.Image:
    page_size = (
        LETTER_LANDSCAPE if source.width > source.height else LETTER_PORTRAIT
    )
    page = Image.new("RGB", page_size, "white")
    draw = ImageDraw.Draw(page)
    title = ImageFont.load_default(size=22)
    draw.text((55, 28), title_text, fill="black", font=title)
    available = (page.width - 110, page.height - 125)
    fitted = ImageOps.contain(
        source.convert("RGB"), available, Image.Resampling.LANCZOS,
    )
    left = (page.width - fitted.width) // 2
    top = 78 + (available[1] - fitted.height) // 2
    page.paste(fitted, (left, top))
    draw.rectangle(
        (left - 1, top - 1, left + fitted.width, top + fitted.height),
        outline=(170, 170, 170),
    )
    return page


def export_blueprint_pdf(
    path: str | Path, overview_path: str | Path, page_paths,
    plan, source_name: str, project=None,
) -> None:
    rows_per_page = 30
    chunks = [
        plan.rows[index:index + rows_per_page]
        for index in range(0, len(plan.rows), rows_per_page)
    ] or [()]
    summary_pages = [
        _summary_page(
            plan, source_name, rows, index + 1, len(chunks), project,
        )
        for index, rows in enumerate(chunks)
    ]
    with Image.open(overview_path) as overview:
        master_page = _printable_image_page(
            overview, f"{source_name} — Numbered Master Blueprint",
        )
    pages = [master_page, *summary_pages]
    for index, page_path in enumerate(page_paths, start=1):
        with Image.open(page_path) as detail:
            pages.append(
                _printable_image_page(detail, f"Detail Build Page {index}")
            )
    try:
        pages[0].save(
            path, "PDF", save_all=True, append_images=pages[1:],
            resolution=PRINT_DPI,
        )
    finally:
        for page in pages:
            page.close()
