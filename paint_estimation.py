"""Paint-consumption estimates for cartridge mosaic production."""

from dataclasses import dataclass
from math import ceil


SQ_FT_PER_556_CARTRIDGE = 0.018
MILLILITERS_PER_GALLON = 3785.411784
FLUID_OUNCES_PER_GALLON = 128.0
STANDARD_CONTAINER_OUNCES = (("gallon", 128.0), ("quart", 32.0), ("sample", 8.0))


def container_plan(fluid_ounces: float) -> tuple[tuple[str, int], ...]:
    """Round an estimate up into common retail paint-container sizes."""
    remaining = max(0.0, fluid_ounces)
    result = []
    for name, size in STANDARD_CONTAINER_OUNCES[:-1]:
        count = int(remaining // size)
        if count:
            result.append((name, count))
            remaining -= count * size
    if remaining > 0:
        result.append((STANDARD_CONTAINER_OUNCES[-1][0], ceil(remaining / 8.0)))
    return tuple(result)


def container_plan_text(fluid_ounces: float) -> str:
    plan = container_plan(fluid_ounces)
    return ", ".join(f"{count} {name}{'' if count == 1 else 's'}" for name, count in plan) or "None"


@dataclass(frozen=True, slots=True)
class PaintEstimate:
    """Estimated coating consumed for one mosaic color."""

    milliliters: float
    fluid_ounces: float
    gallons: float

    def estimated_cost(self, price_per_gallon: float) -> float:
        if price_per_gallon < 0:
            raise ValueError("Paint price cannot be negative.")
        return self.gallons * price_per_gallon

    def display_text(self) -> str:
        if self.milliliters >= 1000:
            metric = f"{self.milliliters / 1000:.2f} L"
        else:
            metric = f"{self.milliliters:.0f} mL"
        return f"{metric}\n{self.fluid_ounces:.2f} fl oz"


@dataclass(frozen=True, slots=True)
class PaintUsageEstimator:
    """Estimate paint film consumed from surface area and spread rate.

    The cartridge area is an engineering approximation for the exterior of a
    complete 5.56×45 mm cartridge. ``process_factor`` accounts for dipping,
    drainage, transfer losses, and practical waste.
    """

    coverage_sq_ft_per_gallon: float = 350.0
    process_factor: float = 2.0
    cartridges_per_tile: int = 4
    cartridge_area_sq_ft: float = SQ_FT_PER_556_CARTRIDGE

    def __post_init__(self) -> None:
        if self.coverage_sq_ft_per_gallon <= 0:
            raise ValueError("Paint coverage must be greater than zero.")
        if self.process_factor <= 0:
            raise ValueError("Paint process factor must be greater than zero.")
        if self.cartridges_per_tile <= 0 or self.cartridge_area_sq_ft <= 0:
            raise ValueError("Cartridge quantity and surface area must be positive.")

    def estimate(self, tile_count: int) -> PaintEstimate:
        if tile_count < 0:
            raise ValueError("Tile count cannot be negative.")
        surface_area = (
            tile_count
            * self.cartridges_per_tile
            * self.cartridge_area_sq_ft
        )
        gallons = (
            surface_area
            / self.coverage_sq_ft_per_gallon
            * self.process_factor
        )
        return PaintEstimate(
            milliliters=gallons * MILLILITERS_PER_GALLON,
            fluid_ounces=gallons * FLUID_OUNCES_PER_GALLON,
            gallons=gallons,
        )
