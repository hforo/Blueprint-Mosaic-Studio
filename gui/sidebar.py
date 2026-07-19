"""Tabbed editor controls displayed beside the graphics canvas."""

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QHeaderView, QPushButton, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from color_matching import SherwinWilliamsMatcher
from paint_estimation import PaintUsageEstimator
from paint_plan import SherwinWilliamsPaintPlan


RGB = tuple[int, int, int]


class PalettePanel(QWidget):
    """Number-to-color legend for the currently generated mosaic."""

    def __init__(self, matcher: SherwinWilliamsMatcher, parent=None) -> None:
        super().__init__(parent)
        self.matcher = matcher
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.summary = QLabel("Generate a blueprint to see its color legend.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            [
                "#", "Mosaic", "Value", "Closest Sherwin-Williams",
                "Match", "Est. paint", "Tiles",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 46)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 46)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        disclaimer = QLabel(
            "Digital nearest match only. Confirm the selection with a physical "
            "Sherwin-Williams color chip before purchasing paint."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: palette(mid); font-size: 11px;")
        disclaimer.setToolTip(
            "Screen colors, lighting, sheen, and paint substrate can change "
            "the appearance of a finished color."
        )
        layout.addWidget(disclaimer)

    def set_palette(
        self,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        paint_estimator: PaintUsageEstimator,
    ) -> None:
        """Display palette colors using the same numbers as the mosaic cells."""
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(palette))
        total_tiles = sum(color_counts.values())

        for row, color_number in enumerate(sorted(palette)):
            red, green, blue = palette[color_number]
            color = QColor(red, green, blue)
            paint_match = self.matcher.nearest((red, green, blue))
            paint = paint_match.color
            match_color = QColor(*paint.rgb)
            number_item = QTableWidgetItem(str(color_number))
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            swatch_item = QTableWidgetItem()
            swatch_item.setBackground(color)
            swatch_item.setToolTip(color.name(QColor.NameFormat.HexRgb).upper())

            value_item = QTableWidgetItem(
                f"{color.name(QColor.NameFormat.HexRgb).upper()}\n"
                f"RGB {red}, {green}, {blue}"
            )
            tile_count = color_counts.get(color_number, 0)
            count_item = QTableWidgetItem(f"{tile_count:,}")
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            paint_estimate = paint_estimator.estimate(tile_count)
            estimate_item = QTableWidgetItem(paint_estimate.display_text())
            estimate_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            estimate_item.setToolTip(
                "Estimated coating consumed; excludes paint needed to fill "
                "the dipping container"
            )
            paint_item = QTableWidgetItem(
                f"{paint.display_code} · {paint.name}\n"
                f"{paint.hex_value} · ΔE {paint_match.delta_e:.1f}"
            )
            paint_item.setToolTip(
                "Nearest ColorSnap color by CIE Lab perceptual distance"
            )
            match_swatch_item = QTableWidgetItem()
            match_swatch_item.setBackground(match_color)
            match_swatch_item.setToolTip(
                f"{paint.display_code} {paint.name} ({paint.hex_value})"
            )

            self.table.setItem(row, 0, number_item)
            self.table.setItem(row, 1, swatch_item)
            self.table.setItem(row, 2, value_item)
            self.table.setItem(row, 3, paint_item)
            self.table.setItem(row, 4, match_swatch_item)
            self.table.setItem(row, 5, estimate_item)
            self.table.setItem(row, 6, count_item)
            self.table.setRowHeight(row, 46)

        total_estimate = paint_estimator.estimate(total_tiles)
        total_estimate_text = total_estimate.display_text().replace("\n", " · ")
        self.summary.setText(
            f"{len(palette)} colors · {total_tiles:,} numbered squares\n"
            f"Estimated coating: {total_estimate_text}\n"
            f"Assumptions: 4 cartridges/square · "
            f"{paint_estimator.coverage_sq_ft_per_gallon:.0f} ft²/gal · "
            f"{paint_estimator.process_factor:.2f}× dip/waste"
        )
        self.table.setUpdatesEnabled(True)


class SummaryPanel(QWidget):
    """Aggregated Sherwin-Williams purchasing and paint-use summary."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.summary = QLabel("Generate a blueprint to create a paint summary.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(
            ["Color", "Sherwin-Williams", "Mosaic #", "Tiles", "Paint", "Cost"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 50)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        note = QLabel(
            "Cost is proportional paint consumed at the configured gallon price. "
            "It excludes minimum container sizes, tint/base differences, tax, and "
            "paint retained in the dipping vessel."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(note)

    def set_plan(self, plan: SherwinWilliamsPaintPlan) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(plan.rows))
        total_tiles = 0
        for row_index, row in enumerate(plan.rows):
            swatch = QTableWidgetItem()
            swatch.setBackground(QColor(*row.paint.rgb))
            paint_name = QTableWidgetItem(
                f"{row.paint.display_code} · {row.paint.name}\n"
                f"{row.paint.hex_value}"
            )
            numbers = QTableWidgetItem(row.palette_numbers_text)
            tiles = QTableWidgetItem(f"{row.tile_count:,}")
            tiles.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            amount = QTableWidgetItem(row.estimate.display_text())
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            cost = QTableWidgetItem(f"${row.estimated_cost:,.2f}")
            cost.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            for column, item in enumerate(
                (swatch, paint_name, numbers, tiles, amount, cost)
            ):
                self.table.setItem(row_index, column, item)
            self.table.setRowHeight(row_index, 46)
            total_tiles += row.tile_count

        total_amount = plan.total_estimate.display_text().replace("\n", " · ")
        self.summary.setText(
            f"{len(plan.rows)} different Sherwin-Williams colors\n"
            f"{total_tiles:,} numbered squares · {total_amount}\n"
            f"Estimated proportional paint cost: "
            f"${plan.total_estimated_cost:,.2f} at "
            f"${plan.price_per_gallon:,.2f}/gal"
        )
        self.table.setUpdatesEnabled(True)


class SettingsPanel(QWidget):
    """Mosaic generation settings exposed as a reusable panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel("Mosaic Settings")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)

        settings = QGroupBox("Generation")
        form = QFormLayout(settings)
        self.grid = QSpinBox()
        self.grid.setRange(8, 500)
        self.grid.setValue(96)
        self.grid.setSuffix(" columns")
        form.addRow("Grid width", self.grid)
        self.tile_size = QDoubleSpinBox()
        self.tile_size.setRange(0.01, 100.0)
        self.tile_size.setDecimals(3)
        self.tile_size.setSingleStep(0.05)
        self.tile_size.setValue(0.75)
        self.tile_size.setSuffix(" in")
        self.tile_size.setToolTip(
            "Physical width and height of one finished mosaic tile"
        )
        form.addRow("Tile size", self.tile_size)
        self.colors = QSpinBox()
        self.colors.setRange(2, 256)
        self.colors.setValue(64)
        form.addRow("Colors", self.colors)
        self.palette = QComboBox()
        self.palette.addItems(["Image-derived", "Sherwin-Williams", "Custom"])
        self.palette.setEnabled(False)
        self.palette.setToolTip("Custom palettes are planned for a future milestone")
        form.addRow("Palette", self.palette)
        self.dither = QCheckBox("Enable dithering")
        self.dither.setChecked(True)
        form.addRow(self.dither)
        self.paint_coverage = QDoubleSpinBox()
        self.paint_coverage.setRange(1.0, 2000.0)
        self.paint_coverage.setDecimals(0)
        self.paint_coverage.setValue(350.0)
        self.paint_coverage.setSuffix(" ft²/gal")
        self.paint_coverage.setToolTip(
            "Manufacturer spread rate; Sherwin-Williams typically estimates "
            "350–400 square feet per gallon"
        )
        form.addRow("Paint coverage", self.paint_coverage)
        self.paint_process_factor = QDoubleSpinBox()
        self.paint_process_factor.setRange(1.0, 10.0)
        self.paint_process_factor.setDecimals(2)
        self.paint_process_factor.setSingleStep(0.25)
        self.paint_process_factor.setValue(2.0)
        self.paint_process_factor.setSuffix("×")
        self.paint_process_factor.setToolTip(
            "Multiplier for dipping, drainage, transfer loss, and waste"
        )
        form.addRow("Dip/waste factor", self.paint_process_factor)
        self.paint_price = QDoubleSpinBox()
        self.paint_price.setRange(0.0, 1000.0)
        self.paint_price.setDecimals(2)
        self.paint_price.setSingleStep(5.0)
        self.paint_price.setValue(64.0)
        self.paint_price.setPrefix("$")
        self.paint_price.setSuffix(" / gal")
        self.paint_price.setToolTip(
            "Planning assumption only; enter the actual price of your chosen "
            "paint product and finish"
        )
        form.addRow("Paint price", self.paint_price)
        layout.addWidget(settings)

        self.generate = QPushButton("Generate Blueprint")
        self.generate.setMinimumHeight(38)
        layout.addWidget(self.generate)
        layout.addStretch()


class Sidebar(QTabWidget):
    """Tabbed sidebar containing settings and the generated color legend."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(620)
        self.matcher = SherwinWilliamsMatcher()
        self.settings_panel = SettingsPanel(self)
        self.palette_panel = PalettePanel(self.matcher, self)
        self.summary_panel = SummaryPanel(self)
        self.addTab(self.settings_panel, "Settings")
        self.addTab(self.palette_panel, "Colors")
        self.addTab(self.summary_panel, "Summary")

        # Preserve the concise control API used by MainWindow.
        self.grid = self.settings_panel.grid
        self.tile_size = self.settings_panel.tile_size
        self.colors = self.settings_panel.colors
        self.palette = self.settings_panel.palette
        self.dither = self.settings_panel.dither
        self.paint_coverage = self.settings_panel.paint_coverage
        self.paint_process_factor = self.settings_panel.paint_process_factor
        self.paint_price = self.settings_panel.paint_price
        self.generate = self.settings_panel.generate

    def set_palette(
        self,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        paint_plan: SherwinWilliamsPaintPlan | None = None,
    ) -> None:
        estimator = self.paint_estimator()
        if paint_plan is None:
            paint_plan = self.create_paint_plan(palette, color_counts)
        self.palette_panel.set_palette(palette, color_counts, estimator)
        self.summary_panel.set_plan(paint_plan)
        self.setCurrentWidget(self.summary_panel)

    def paint_estimator(self) -> PaintUsageEstimator:
        return PaintUsageEstimator(
            coverage_sq_ft_per_gallon=self.paint_coverage.value(),
            process_factor=self.paint_process_factor.value(),
        )

    def create_paint_plan(
        self,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
    ) -> SherwinWilliamsPaintPlan:
        return SherwinWilliamsPaintPlan.build(
            palette,
            color_counts,
            self.matcher,
            self.paint_estimator(),
            self.paint_price.value(),
        )
