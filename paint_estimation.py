"""Paint-consumption estimates for square-tile mosaic production."""

from dataclasses import dataclass
from math import ceil, pi


MILLILITERS_PER_GALLON = 3785.411784
FLUID_OUNCES_PER_GALLON = 128.0
STANDARD_CONTAINER_OUNCES = (("gallon", 128.0), ("quart", 32.0), ("sample", 8.0))
MM_PER_INCH = 25.4
CARTRIDGE_556_CASE_LENGTH_MM = 44.70
CARTRIDGE_556_OVERALL_LENGTH_MM = 57.40
CARTRIDGE_556_CASE_DIAMETER_MM = 9.58
CARTRIDGE_556_PROJECTILE_DIAMETER_MM = 5.70


def vertical_556_cartridge_surface_area_sq_in(quantity: int = 4) -> float:
    """Approximate the complete exterior area of upright 5.56 cartridges.

    Each piece is modeled as a case cylinder plus an exposed-projectile
    cylinder. The circular base and tip are included. Point contacts between
    adjacent vertical pieces do not remove measurable coated area.
    """
    if quantity <= 0:
        raise ValueError("Cartridge quantity must be positive.")
    exposed_projectile_length = (
        CARTRIDGE_556_OVERALL_LENGTH_MM - CARTRIDGE_556_CASE_LENGTH_MM
    )
    lateral_case = (
        pi * CARTRIDGE_556_CASE_DIAMETER_MM * CARTRIDGE_556_CASE_LENGTH_MM
    )
    lateral_projectile = (
        pi * CARTRIDGE_556_PROJECTILE_DIAMETER_MM * exposed_projectile_length
    )
    base = pi * (CARTRIDGE_556_CASE_DIAMETER_MM / 2) ** 2
    tip = pi * (CARTRIDGE_556_PROJECTILE_DIAMETER_MM / 2) ** 2
    return quantity * (lateral_case + lateral_projectile + base + tip) / MM_PER_INCH ** 2


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
    """Estimate paint consumed from coated tile area and spread rate."""

    coverage_sq_ft_per_gallon: float = 350.0
    process_factor: float = 2.0
    tile_surface_area_sq_in: float = 0.5625

    def __post_init__(self) -> None:
        if self.coverage_sq_ft_per_gallon <= 0:
            raise ValueError("Paint coverage must be greater than zero.")
        if self.process_factor <= 0:
            raise ValueError("Paint process factor must be greater than zero.")
        if self.tile_surface_area_sq_in <= 0:
            raise ValueError("Coated surface area per tile must be positive.")

    def estimate(self, tile_count: int) -> PaintEstimate:
        if tile_count < 0:
            raise ValueError("Tile count cannot be negative.")
        surface_area = tile_count * self.tile_surface_area_sq_in / 144.0
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
