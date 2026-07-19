"""Paint-consumption estimates for cartridge mosaic production."""

from dataclasses import dataclass


SQ_FT_PER_556_CARTRIDGE = 0.018
MILLILITERS_PER_GALLON = 3785.411784
FLUID_OUNCES_PER_GALLON = 128.0


@dataclass(frozen=True, slots=True)
class PaintEstimate:
    """Estimated coating consumed for one mosaic color."""

    milliliters: float
    fluid_ounces: float
    gallons: float

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
