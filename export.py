"""Offline exports for generated blueprint packages and shopping lists."""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from paint_estimation import container_plan_text


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


def _summary_page(plan, source_name: str, rows, page_number: int, total_pages: int) -> Image.Image:
    width, height = 1650, 2200
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=34)
    body = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=18)
    draw.text((80, 70), f"{source_name} — Paint Summary ({page_number}/{total_pages})", fill="black", font=title)
    draw.text((80, 130), f"Catalog: {plan.catalog_name}", fill="black", font=body)
    y = 200
    for row in rows:
        draw.rectangle((80, y, 125, y + 45), fill=row.paint.rgb, outline="black")
        draw.text(
            (145, y),
            f"{row.paint.display_code}  {row.paint.name}  |  {row.tile_count:,} tiles  |  "
            f"{container_plan_text(row.estimate.fluid_ounces)}",
            fill="black", font=small,
        )
        y += 58
    draw.text(
        (80, height - 90),
        "Container suggestions assume standard 8 fl oz samples, 32 fl oz quarts, and 128 fl oz gallons; verify availability with the manufacturer.",
        fill=(80, 80, 80), font=small,
    )
    return image


def export_blueprint_pdf(
    path: str | Path, overview_path: str | Path, page_paths,
    plan, source_name: str,
) -> None:
    rows_per_page = 32
    chunks = [plan.rows[index:index + rows_per_page] for index in range(0, len(plan.rows), rows_per_page)] or [()]
    summary_pages = [
        _summary_page(plan, source_name, rows, index + 1, len(chunks))
        for index, rows in enumerate(chunks)
    ]
    pages = [Image.open(overview_path).convert("RGB"), *summary_pages]
    pages.extend(Image.open(page).convert("RGB") for page in page_paths)
    try:
        pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    finally:
        for page in pages:
            page.close()
