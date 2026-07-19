"""Aggregate mosaic palette colors into a Sherwin-Williams paint plan."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from color_matching import PaintColor, SherwinWilliamsMatcher
from paint_estimation import PaintEstimate, PaintUsageEstimator


RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class PaintPlanRow:
    """Aggregated requirements for one Sherwin-Williams paint color."""

    paint: PaintColor
    palette_numbers: tuple[int, ...]
    tile_count: int
    estimate: PaintEstimate
    estimated_cost: float

    @property
    def palette_numbers_text(self) -> str:
        return ", ".join(str(number) for number in self.palette_numbers)


@dataclass(frozen=True, slots=True)
class SherwinWilliamsPaintPlan:
    """Paint requirements and preview-color overrides for a mosaic."""

    rows: tuple[PaintPlanRow, ...]
    color_overrides: Mapping[int, RGB]
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
    ) -> SherwinWilliamsPaintPlan:
        if price_per_gallon < 0:
            raise ValueError("Paint price cannot be negative.")

        grouped: dict[str, dict[str, object]] = {}
        overrides: dict[int, RGB] = {}
        for palette_number in sorted(palette):
            match = matcher.nearest(palette[palette_number])
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
            rows.append(
                PaintPlanRow(
                    paint=paint,
                    palette_numbers=tuple(int(number) for number in numbers),
                    tile_count=tile_count,
                    estimate=estimate,
                    estimated_cost=estimate.estimated_cost(price_per_gallon),
                )
            )
        rows.sort(key=lambda row: row.paint.code)
        total_estimate = estimator.estimate(sum(color_counts.values()))
        return cls(
            rows=tuple(rows),
            color_overrides=overrides,
            total_estimate=total_estimate,
            total_estimated_cost=total_estimate.estimated_cost(price_per_gallon),
            price_per_gallon=price_per_gallon,
        )
