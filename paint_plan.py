"""Aggregate mosaic palette colors into a Sherwin-Williams paint plan."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from color_matching import (
    PaintColor,
    PaintMatch,
    SherwinWilliamsMatcher,
    delta_e_cie76,
    rgb_to_lab,
)
from paint_estimation import PaintEstimate, PaintUsageEstimator


RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class PaintPlanRow:
    """Aggregated requirements for one Sherwin-Williams paint color."""

    paint: PaintColor
    palette_numbers: tuple[int, ...]
    coordinate_ranges: tuple[str, ...]
    coordinate_count: int
    tile_count: int
    estimate: PaintEstimate
    estimated_cost: float

    @property
    def palette_numbers_text(self) -> str:
        return ", ".join(str(number) for number in self.palette_numbers)

    def coordinates_text(self, maximum_ranges: int = 8) -> str:
        if not self.coordinate_ranges:
            return "—"
        visible = self.coordinate_ranges[:maximum_ranges]
        text = "; ".join(visible)
        remaining = len(self.coordinate_ranges) - len(visible)
        if remaining:
            text += f"; +{remaining:,} more"
        return text


@dataclass(frozen=True, slots=True)
class SherwinWilliamsPaintPlan:
    """Paint requirements and preview-color overrides for a mosaic."""

    catalog_name: str
    rows: tuple[PaintPlanRow, ...]
    color_overrides: Mapping[int, RGB]
    matches: Mapping[int, PaintMatch]
    total_estimate: PaintEstimate
    total_estimated_cost: float
    price_per_gallon: float

    @classmethod
    def build(
        cls,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        matcher: SherwinWilliamsMatcher,
        estimator: PaintUsageEstimator,
        price_per_gallon: float,
        target_color_count: int | None = None,
        positions_by_palette: Mapping[int, list[tuple[int, int]]] | None = None,
        override_codes: Mapping[int, str] | None = None,
    ) -> SherwinWilliamsPaintPlan:
        if price_per_gallon < 0:
            raise ValueError("Paint price cannot be negative.")

        active_numbers = [
            number for number in palette if color_counts.get(number, 0) > 0
        ]
        if not active_numbers:
            raise ValueError("Cannot build a paint plan without active colors.")
        if target_color_count is None:
            target_color_count = len(active_numbers)
        if target_color_count <= 0:
            raise ValueError("Target SW color count must be greater than zero.")
        target_color_count = min(target_color_count, len(active_numbers))

        seed_numbers = cls._select_representative_colors(
            active_numbers,
            palette,
            color_counts,
            target_color_count,
        )
        selected_matches: dict[int, PaintMatch] = {}
        used_codes: set[str] = set()
        for palette_number in seed_numbers:
            match = matcher.nearest_available(palette[palette_number], used_codes)
            selected_matches[palette_number] = match
            used_codes.add(match.color.code)

        matches: dict[int, PaintMatch] = {}
        for palette_number in active_numbers:
            if palette_number in selected_matches:
                matches[palette_number] = selected_matches[palette_number]
                continue
            source_lab = rgb_to_lab(palette[palette_number])
            paint = min(
                (match.color for match in selected_matches.values()),
                key=lambda candidate: delta_e_cie76(source_lab, candidate.lab),
            )
            matches[palette_number] = PaintMatch(
                paint,
                delta_e_cie76(source_lab, paint.lab),
            )

        for palette_number, code in (override_codes or {}).items():
            if palette_number not in palette:
                continue
            paint = matcher.by_code(code)
            if paint is None:
                continue
            matches[palette_number] = PaintMatch(
                paint,
                delta_e_cie76(rgb_to_lab(palette[palette_number]), paint.lab),
            )

        grouped: dict[str, dict[str, object]] = {}
        overrides: dict[int, RGB] = {}
        for palette_number in sorted(active_numbers):
            match = matches[palette_number]
            paint = match.color
            overrides[palette_number] = paint.rgb
            group = grouped.setdefault(
                paint.code,
                {"paint": paint, "numbers": [], "tiles": 0},
            )
            numbers = group["numbers"]
            if isinstance(numbers, list):
                numbers.append(palette_number)
            group["tiles"] = int(group["tiles"]) + color_counts.get(
                palette_number, 0
            )

        rows = []
        for group in grouped.values():
            paint = group["paint"]
            numbers = group["numbers"]
            tile_count = int(group["tiles"])
            if not isinstance(paint, PaintColor) or not isinstance(numbers, list):
                raise TypeError("Invalid paint-plan aggregation state.")
            estimate = estimator.estimate(tile_count)
            positions = []
            if positions_by_palette is not None:
                for palette_number in numbers:
                    positions.extend(
                        positions_by_palette.get(int(palette_number), [])
                    )
            coordinate_ranges = _compress_coordinates(positions)
            rows.append(
                PaintPlanRow(
                    paint=paint,
                    palette_numbers=tuple(int(number) for number in numbers),
                    coordinate_ranges=coordinate_ranges,
                    coordinate_count=len(positions),
                    tile_count=tile_count,
                    estimate=estimate,
                    estimated_cost=estimate.estimated_cost(price_per_gallon),
                )
            )
        rows.sort(key=lambda row: row.paint.code)
        total_estimate = estimator.estimate(sum(color_counts.values()))
        return cls(
            catalog_name=matcher.catalog_name,
            rows=tuple(rows),
            color_overrides=overrides,
            matches=matches,
            total_estimate=total_estimate,
            total_estimated_cost=total_estimate.estimated_cost(price_per_gallon),
            price_per_gallon=price_per_gallon,
        )

    @staticmethod
    def _select_representative_colors(
        active_numbers: list[int],
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        target_count: int,
    ) -> list[int]:
        """Select dominant, well-separated image colors for paint matching."""
        first = max(
            active_numbers,
            key=lambda number: (color_counts.get(number, 0), -number),
        )
        selected = [first]
        labs = {number: rgb_to_lab(palette[number]) for number in active_numbers}
        while len(selected) < target_count:
            remaining = [
                number for number in active_numbers if number not in selected
            ]
            next_number = max(
                remaining,
                key=lambda number: (
                    min(
                        delta_e_cie76(labs[number], labs[chosen])
                        for chosen in selected
                    ),
                    color_counts.get(number, 0),
                    -number,
                ),
            )
            selected.append(next_number)
        return selected


def _compress_coordinates(
    positions: list[tuple[int, int]],
) -> tuple[str, ...]:
    """Compress zero-based cell positions into row-wise A1 coordinate ranges."""
    rows: dict[int, list[int]] = {}
    for row, column in positions:
        rows.setdefault(row, []).append(column)
    ranges = []
    for row in sorted(rows):
        columns = sorted(set(rows[row]))
        if not columns:
            continue
        start = previous = columns[0]
        for column in columns[1:] + [columns[-1] + 2]:
            if column == previous + 1:
                previous = column
                continue
            first = f"{_column_name(start)}{row + 1}"
            last = f"{_column_name(previous)}{row + 1}"
            ranges.append(first if start == previous else f"{first}:{last}")
            start = previous = column
    return tuple(ranges)


def _column_name(index: int) -> str:
    result = ""
    while index >= 0:
        result = chr(index % 26 + 65) + result
        index = index // 26 - 1
    return result
