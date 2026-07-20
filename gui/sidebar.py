"""Tabbed editor controls displayed beside the graphics canvas."""

from collections.abc import Mapping
from math import pi
from pathlib import Path
import shutil

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QDoubleSpinBox, QFileDialog, QHeaderView, QMessageBox, QPushButton, QSpinBox,
    QTabWidget, QTableWidget,
    QListWidget, QListWidgetItem, QTableWidgetItem, QVBoxLayout, QWidget,
)

from color_matching import SherwinWilliamsMatcher
from paint_estimation import (
    PaintUsageEstimator, container_plan_text,
    vertical_556_cartridge_surface_area_sq_in,
)
from paint_plan import SherwinWilliamsPaintPlan
from pages import PageSection


RGB = tuple[int, int, int]


class PalettePanel(QWidget):
    """Number-to-color legend for the currently generated mosaic."""

    color_selected = Signal(object)
    paint_override_requested = Signal(int)
    paint_unlock_requested = Signal(object)
    merge_requested = Signal(object)

    def __init__(self, matcher: SherwinWilliamsMatcher, parent=None) -> None:
        super().__init__(parent)
        self.matcher = matcher
        self._suppress_selection_release = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.summary = QLabel("Generate a blueprint to see its color legend.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            [
                "#", "Mosaic", "Value", "Closest paint color",
                "Match", "Est. paint", "Tiles",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._emit_selected_colors)
        self.table.viewport().installEventFilter(self)
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
        actions = QHBoxLayout()
        self.change_paint = QPushButton("Choose / lock paint…")
        self.change_paint.clicked.connect(self._request_paint_override)
        actions.addWidget(self.change_paint)
        self.unlock_paint = QPushButton("Unlock")
        self.unlock_paint.clicked.connect(
            lambda: self.paint_unlock_requested.emit(self.selected_palette_numbers())
        )
        actions.addWidget(self.unlock_paint)
        self.merge_colors = QPushButton("Merge selected into first")
        self.merge_colors.clicked.connect(self._request_merge)
        actions.addWidget(self.merge_colors)
        layout.addLayout(actions)
        self.edit_tiles = QCheckBox("Edit tiles by clicking the mosaic")
        self.edit_tiles.setToolTip(
            "Select one palette row, then click mosaic squares to repaint them."
        )
        layout.addWidget(self.edit_tiles)
        disclaimer = QLabel(
            "Digital nearest match only. Confirm the selection with a physical "
            "manufacturer color chip before purchasing paint."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: palette(mid); font-size: 11px;")
        disclaimer.setToolTip(
            "Screen colors, lighting, sheen, and paint substrate can change "
            "the appearance of a finished color."
        )
        layout.addWidget(disclaimer)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.MouseButtonRelease
            and self._suppress_selection_release
        ):
            self._suppress_selection_release = False
            return True
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            index = self.table.indexAt(event.position().toPoint())
            if index.isValid() and self.table.selectionModel().isRowSelected(
                index.row(), index.parent()
            ):
                self.table.selectionModel().select(
                    index,
                    self.table.selectionModel().SelectionFlag.Deselect
                    | self.table.selectionModel().SelectionFlag.Rows,
                )
                self._suppress_selection_release = True
                return True
        return super().eventFilter(watched, event)

    def set_palette(
        self,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        paint_estimator: PaintUsageEstimator,
        paint_plan: SherwinWilliamsPaintPlan,
    ) -> None:
        """Display palette colors using the same numbers as the mosaic cells."""
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(palette))
        total_tiles = sum(color_counts.values())

        for row, color_number in enumerate(sorted(palette)):
            red, green, blue = palette[color_number]
            color = QColor(red, green, blue)
            paint_match = paint_plan.matches[color_number]
            paint = paint_match.color
            match_color = QColor(*paint.rgb)
            number_item = QTableWidgetItem(str(color_number))
            number_item.setData(Qt.ItemDataRole.UserRole, color_number)
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
                "Estimated coating consumed from the configured coated area per tile"
            )
            paint_item = QTableWidgetItem(
                f"{paint.display_code} · {paint.name}\n"
                f"{paint.hex_value} · ΔE {paint_match.delta_e:.1f}"
            )
            paint_item.setToolTip(
                "Nearest catalog color by CIE Lab perceptual distance"
            )
            if paint_match.delta_e >= 15:
                paint_item.setForeground(QColor(180, 70, 0))
                paint_item.setToolTip(
                    "Poor digital match (ΔE 15 or higher). Verify with a physical chip."
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
            f"Assumptions: {paint_estimator.tile_surface_area_sq_in:.3f} in² coated/tile · "
            f"{paint_estimator.coverage_sq_ft_per_gallon:.0f} ft²/gal · "
            f"{paint_estimator.process_factor:.2f}× application/waste"
        )
        self.table.setUpdatesEnabled(True)

    def selected_palette_numbers(self) -> tuple[int, ...]:
        numbers = set()
        for index in self.table.selectionModel().selectedRows(0):
            item = self.table.item(index.row(), 0)
            if item is not None:
                numbers.add(int(item.data(Qt.ItemDataRole.UserRole)))
        return tuple(sorted(numbers))

    def _request_paint_override(self) -> None:
        numbers = self.selected_palette_numbers()
        if numbers:
            self.paint_override_requested.emit(numbers[0])

    def _emit_selected_colors(self) -> None:
        self.color_selected.emit(self.selected_palette_numbers())

    def _request_merge(self) -> None:
        numbers = self.selected_palette_numbers()
        if len(numbers) > 1:
            self.merge_requested.emit(numbers)


class SummaryPanel(QWidget):
    """Aggregated Sherwin-Williams purchasing and paint-use summary."""

    color_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._suppress_selection_release = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.summary = QLabel("Generate a blueprint to create a paint summary.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels(
            [
                "Color", "Paint color", "Catalog", "Coordinates", "Tiles",
                "Paint", "Buy", "Cost",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._emit_selected_color)
        self.table.viewport().installEventFilter(self)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 50)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        note = QLabel(
            "Cost is proportional paint consumed at the configured gallon price. "
            "It excludes minimum container sizes, tint/base differences, tax, and "
            "paint retained in application tools or containers."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(note)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.MouseButtonRelease
            and self._suppress_selection_release
        ):
            self._suppress_selection_release = False
            return True
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            index = self.table.indexAt(event.position().toPoint())
            if index.isValid() and self.table.selectionModel().isRowSelected(
                index.row(), index.parent()
            ):
                self.table.selectionModel().clear()
                self._suppress_selection_release = True
                return True
        return super().eventFilter(watched, event)

    def set_plan(self, plan: SherwinWilliamsPaintPlan) -> None:
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(plan.rows))
        total_tiles = 0
        poor_matches = 0
        for row_index, row in enumerate(plan.rows):
            swatch = QTableWidgetItem()
            swatch.setBackground(QColor(*row.paint.rgb))
            paint_name = QTableWidgetItem(
                f"{row.paint.display_code} · {row.paint.name}\n"
                f"{row.paint.hex_value}"
            )
            paint_name.setData(
                Qt.ItemDataRole.UserRole,
                row.palette_numbers,
            )
            worst_delta = max(
                (plan.matches[number].delta_e for number in row.palette_numbers),
                default=0.0,
            )
            if worst_delta >= 15:
                poor_matches += 1
                paint_name.setForeground(QColor(180, 70, 0))
                paint_name.setToolTip(
                    f"Poor digital match (worst ΔE {worst_delta:.1f}). Verify with a physical chip."
                )
            catalog = QTableWidgetItem(plan.catalog_name)
            coordinates = QTableWidgetItem(row.coordinates_text())
            coordinates.setToolTip(
                f"{row.coordinate_count:,} squares\n"
                + "; ".join(row.coordinate_ranges[:200])
            )
            tiles = QTableWidgetItem(f"{row.tile_count:,}")
            tiles.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            amount = QTableWidgetItem(row.estimate.display_text())
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            containers = QTableWidgetItem(
                container_plan_text(row.estimate.fluid_ounces)
            )
            containers.setToolTip(
                "Planning estimate using standard 8 fl oz samples, 32 fl oz quarts, and 128 fl oz gallons. Verify brand availability."
            )
            cost = QTableWidgetItem(f"${row.estimated_cost:,.2f}")
            cost.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            for column, item in enumerate(
                (swatch, paint_name, catalog, coordinates, tiles, amount, containers, cost)
            ):
                self.table.setItem(row_index, column, item)
            self.table.setRowHeight(row_index, 46)
            total_tiles += row.tile_count

        total_amount = plan.total_estimate.display_text().replace("\n", " · ")
        self.summary.setText(
            f"Catalog: {plan.catalog_name}\n"
            f"{len(plan.rows)} different paint colors\n"
            f"{total_tiles:,} numbered squares · {total_amount}\n"
            f"Estimated proportional paint cost: "
            f"${plan.total_estimated_cost:,.2f} at "
            f"${plan.price_per_gallon:,.2f}/gal"
            + (
                f"\nWarning: {poor_matches} paint match{'es' if poor_matches != 1 else ''} need physical-chip review."
                if poor_matches else ""
            )
        )
        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)

    def selected_palette_numbers(self) -> tuple[int, ...]:
        selected_rows = self.table.selectionModel().selectedRows(1)
        if not selected_rows:
            return ()
        item = self.table.item(selected_rows[0].row(), 1)
        if item is None:
            return ()
        value = item.data(Qt.ItemDataRole.UserRole)
        return tuple(value) if value else ()

    def select_palette_number(self, palette_number: int) -> bool:
        """Select and reveal the paint row containing a mosaic palette number."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            numbers = item.data(Qt.ItemDataRole.UserRole) if item else ()
            if numbers and palette_number in numbers:
                self.table.setCurrentCell(row, 0)
                self.table.scrollToItem(self.table.item(row, 0))
                return True
        return False

    def _emit_selected_color(self) -> None:
        self.color_selected.emit(self.selected_palette_numbers())


class PagesPanel(QWidget):
    """Navigation list for rendered printable mosaic sections."""

    page_selected = Signal(str)
    source_requested = Signal()
    previous_requested = Signal()
    next_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pressed_page_was_current = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        heading = QLabel("Printable Build Sections")
        heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(heading)
        description = QLabel(
            "Select a section to preview its close-up build page. The red box "
            "shows its location in the complete mosaic."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("← Previous")
        self.previous_button.clicked.connect(self.previous_requested)
        navigation.addWidget(self.previous_button)
        self.source_button = QPushButton("Back to Overview")
        self.source_button.clicked.connect(self.source_requested)
        navigation.addWidget(self.source_button)
        self.next_button = QPushButton("Next →")
        self.next_button.clicked.connect(self.next_requested)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)

        self.page_list = QListWidget(self)
        self.page_list.setIconSize(QSize(180, 140))
        self.page_list.setSpacing(5)
        self.page_list.viewport().installEventFilter(self)
        self.page_list.itemPressed.connect(self._on_item_pressed)
        self.page_list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.page_list, 1)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.page_list.viewport()
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            item = self.page_list.itemAt(event.position().toPoint())
            self._pressed_page_was_current = (
                item is not None and self.page_list.currentItem() is item
            )
        return super().eventFilter(watched, event)

    def set_sections(self, sections: list[PageSection]) -> None:
        previous_path = self.current_page_path()
        self.page_list.blockSignals(True)
        self.page_list.clear()
        restored_item = None
        for section in sections:
            item = QListWidgetItem(
                QIcon(str(section.thumbnail_path)),
                f"{section.title}\n{section.location_text}",
            )
            item.setData(Qt.ItemDataRole.UserRole, str(section.image_path))
            item.setToolTip(f"Preview {section.title}: {section.location_text}")
            self.page_list.addItem(item)
            if previous_path == str(section.image_path):
                restored_item = item
        if restored_item is not None:
            self.page_list.setCurrentItem(restored_item)
        self.page_list.blockSignals(False)

    def current_page_path(self) -> str | None:
        item = self.page_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def select_page(self, image_path: str | Path) -> bool:
        """Select and open the list item for a generated page image."""
        target = str(Path(image_path).resolve())
        for row in range(self.page_list.count()):
            item = self.page_list.item(row)
            value = item.data(Qt.ItemDataRole.UserRole)
            if value and str(Path(str(value)).resolve()) == target:
                if self.page_list.currentItem() is item:
                    self.page_selected.emit(str(value))
                else:
                    self.page_list.setCurrentItem(item)
                self.page_list.scrollToItem(item)
                return True
        return False

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            return
        image_path = current.data(Qt.ItemDataRole.UserRole)
        if image_path:
            self.page_selected.emit(str(image_path))

    def _on_item_pressed(self, item: QListWidgetItem) -> None:
        """Reopen a page when its already-selected list item is clicked."""
        if self._pressed_page_was_current:
            image_path = item.data(Qt.ItemDataRole.UserRole)
            if image_path:
                self.page_selected.emit(str(image_path))


class SettingsPanel(QWidget):
    """Mosaic generation settings exposed as a reusable panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel("Mosaic Settings")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)
        self.generation_status = QLabel("Blueprint not generated")
        self.generation_status.setWordWrap(True)
        self.generation_status.setStyleSheet(
            "padding: 6px; border-radius: 3px; background: #5b3a16; color: #fff3d6;"
        )
        layout.addWidget(self.generation_status)

        settings = QGroupBox("Generation")
        form = QFormLayout(settings)
        self.paint_company = QComboBox()
        form.addRow("Paint company", self.paint_company)
        self.import_catalog = QPushButton("Install paint catalog JSON...")
        form.addRow("Add company", self.import_catalog)
        self.grid = QSpinBox()
        self.grid.setRange(8, 500)
        self.grid.setValue(96)
        self.grid.setSuffix(" columns")
        form.addRow("Grid width", self.grid)
        self.size_mode = QComboBox()
        self.size_mode.addItems(["Set grid columns", "Set finished width"])
        form.addRow("Sizing mode", self.size_mode)
        self.finished_width = QDoubleSpinBox()
        self.finished_width.setRange(1.0, 10000.0)
        self.finished_width.setDecimals(2)
        self.finished_width.setValue(72.0)
        self.finished_width.setSuffix(" in")
        self.finished_width.setEnabled(False)
        form.addRow("Finished width", self.finished_width)
        self.live_preview = QCheckBox("Show pixelated mosaic")
        self.live_preview.setChecked(True)
        self.live_preview.setToolTip(
            "Updates as grid width or image colors change. Turn off to edit "
            "the source-image crop."
        )
        form.addRow("Live preview", self.live_preview)
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
        self.tile_type = QComboBox()
        self.tile_type.addItems([
            "Flat square — one face",
            "Flat square — both faces",
            "Cube / block — all faces",
            "Round disc — one face",
            "Sphere — all surface",
            "4-piece 5.56 cartridge tile",
            "Custom coated area",
        ])
        self.tile_type.setToolTip(
            "Select a preset to calculate coated area per tile, or choose "
            "Custom coated area to enter it manually."
        )
        form.addRow("Tile type", self.tile_type)
        self.tile_surface_area = QDoubleSpinBox()
        self.tile_surface_area.setRange(0.001, 100000.0)
        self.tile_surface_area.setDecimals(3)
        self.tile_surface_area.setSingleStep(0.05)
        self.tile_surface_area.setValue(0.5625)
        self.tile_surface_area.setSuffix(" in²")
        self.tile_surface_area.setToolTip(
            "Total area painted on one tile. Use width × height for one face, "
            "or include edges and other exposed faces when applicable."
        )
        form.addRow("Coated area / tile", self.tile_surface_area)
        self.tile_type.currentTextChanged.connect(self._apply_tile_type_preset)
        self.tile_size.valueChanged.connect(self._apply_tile_type_preset)
        self._apply_tile_type_preset()
        self.image_colors = QSpinBox()
        self.image_colors.setRange(2, 256)
        self.image_colors.setValue(256)
        self.image_colors.setToolTip(
            "Number of colors retained when quantizing the source image"
        )
        form.addRow("Image colors", self.image_colors)
        self.sw_colors = QSpinBox()
        self.sw_colors.setRange(1, 256)
        self.sw_colors.setValue(100)
        self.sw_colors.setToolTip(
            "Requested number of distinct manufacturer paints in the "
            "matched mosaic (limited by the generated image colors)"
        )
        form.addRow("Paint colors", self.sw_colors)
        self.palette = QComboBox()
        self.palette.addItems(["Image-derived", "Sherwin-Williams", "Custom"])
        self.palette.setEnabled(False)
        self.palette.setToolTip("Custom palettes are planned for a future milestone")
        form.addRow("Palette", self.palette)
        self.dither = QComboBox()
        self.dither.addItems(["None", "Light", "Full"])
        self.dither.setCurrentText("None")
        self.dither.setToolTip(
            "None gives clean color regions; Light uses restrained diffusion; "
            "Full preserves more tonal detail but creates a noisier build."
        )
        form.addRow("Dithering", self.dither)
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
            "Multiplier for application loss, transfer loss, retained paint, and waste"
        )
        form.addRow("Application/waste factor", self.paint_process_factor)
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

        preview_group = QGroupBox("Preview and project")
        preview_layout = QVBoxLayout(preview_group)
        self.statistics = QLabel("Open an image to calculate mosaic dimensions.")
        self.statistics.setWordWrap(True)
        preview_layout.addWidget(self.statistics)
        preview_row = QHBoxLayout()
        self.preview_mode = QComboBox()
        self.preview_mode.addItems(
            ["Original", "Pixelated", "Matched paint", "Numbered blueprint"]
        )
        preview_row.addWidget(QLabel("Show"))
        preview_row.addWidget(self.preview_mode, 1)
        preview_layout.addLayout(preview_row)
        layout.addWidget(preview_group)

        self.generate = QPushButton("Generate Blueprint")
        self.generate.setMinimumHeight(38)
        layout.addWidget(self.generate)
        self.generate_pdf = QPushButton("Generate PDF Blueprint…")
        self.generate_pdf.setMinimumHeight(34)
        self.generate_pdf.setEnabled(False)
        self.generate_pdf.setToolTip(
            "Create a printable PDF containing the master blueprint, supplies "
            "and cost sheets, and every detail build page."
        )
        layout.addWidget(self.generate_pdf)
        layout.addStretch()

    def _apply_tile_type_preset(self) -> None:
        tile_width = self.tile_size.value()
        tile_type = self.tile_type.currentText()
        areas = {
            "Flat square — one face": tile_width ** 2,
            "Flat square — both faces": 2 * tile_width ** 2,
            "Cube / block — all faces": 6 * tile_width ** 2,
            "Round disc — one face": pi * (tile_width / 2) ** 2,
            "Sphere — all surface": pi * tile_width ** 2,
            "4-piece 5.56 cartridge tile": (
                vertical_556_cartridge_surface_area_sq_in(4)
            ),
        }
        if tile_type in areas:
            self.tile_surface_area.setValue(areas[tile_type])
            self.tile_surface_area.setEnabled(False)
        else:
            self.tile_surface_area.setEnabled(True)

class Sidebar(QTabWidget):
    """Tabbed sidebar containing settings and the generated color legend."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(620)
        self.catalogs: dict[str, Path] = {}
        data_folder = Path(__file__).resolve().parent.parent / "data"
        for catalog_path in sorted(data_folder.glob("*.json")):
            try:
                matcher = SherwinWilliamsMatcher(catalog_path)
            except ValueError:
                continue
            self.catalogs[matcher.catalog_name] = catalog_path
        if not self.catalogs:
            raise ValueError("No paint catalogs are installed.")
        first_name = next(
            (
                name for name in self.catalogs
                if name.lower().startswith("sherwin-williams")
            ),
            next(iter(self.catalogs)),
        )
        self.matcher = SherwinWilliamsMatcher(self.catalogs[first_name])
        self.paint_overrides: dict[int, str] = {}
        self.settings_panel = SettingsPanel(self)
        self.settings_panel.paint_company.addItems(self.catalogs)
        self.settings_panel.paint_company.setCurrentText(first_name)
        self.palette_panel = PalettePanel(self.matcher, self)
        self.summary_panel = SummaryPanel(self)
        self.pages_panel = PagesPanel(self)
        self.addTab(self.settings_panel, "Settings")
        self.addTab(self.palette_panel, "Colors")
        self.addTab(self.summary_panel, "Summary")
        self.addTab(self.pages_panel, "Pages")
        self.tabBar().installEventFilter(self)

        # Preserve the concise control API used by MainWindow.
        self.grid = self.settings_panel.grid
        self.paint_company = self.settings_panel.paint_company
        self.size_mode = self.settings_panel.size_mode
        self.finished_width = self.settings_panel.finished_width
        self.live_preview = self.settings_panel.live_preview
        self.tile_size = self.settings_panel.tile_size
        self.tile_type = self.settings_panel.tile_type
        self.tile_surface_area = self.settings_panel.tile_surface_area
        self.image_colors = self.settings_panel.image_colors
        self.sw_colors = self.settings_panel.sw_colors
        self.colors = self.image_colors
        self.palette = self.settings_panel.palette
        self.dither = self.settings_panel.dither
        self.statistics = self.settings_panel.statistics
        self.preview_mode = self.settings_panel.preview_mode
        self.paint_coverage = self.settings_panel.paint_coverage
        self.paint_process_factor = self.settings_panel.paint_process_factor
        self.paint_price = self.settings_panel.paint_price
        self.generate = self.settings_panel.generate
        self.generate_pdf = self.settings_panel.generate_pdf
        self.paint_company.currentTextChanged.connect(self._change_catalog)
        self.settings_panel.import_catalog.clicked.connect(self._import_catalog)
        self._change_catalog(first_name)
        self.set_result_tabs_enabled(False)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.tabBar()
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            index = self.tabBar().tabAt(event.position().toPoint())
            if index >= 0 and not self.isTabEnabled(index):
                QMessageBox.information(
                    self,
                    "Generate Blueprint",
                    "The blueprint must be generated before this tab can be opened.",
                )
                return True
        return super().eventFilter(watched, event)

    def _change_catalog(self, catalog_name: str) -> None:
        catalog_path = self.catalogs.get(catalog_name)
        if catalog_path is None:
            return
        self.matcher = SherwinWilliamsMatcher(catalog_path)
        self.palette_panel.matcher = self.matcher
        self.palette_panel.table.horizontalHeaderItem(3).setText(
            f"Closest {catalog_name}"
        )
        self.paint_overrides.clear()

    def set_result_tabs_enabled(self, enabled: bool) -> None:
        """Enable or disable every tab whose contents require generation."""
        for panel in (
            self.palette_panel,
            self.summary_panel,
            self.pages_panel,
        ):
            index = self.indexOf(panel)
            if index >= 0:
                self.setTabEnabled(index, enabled)
        self.generate_pdf.setEnabled(enabled)

    def _import_catalog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Install Paint Catalog", "", "Paint catalog (*.json)",
        )
        if not filename:
            return
        source = Path(filename).resolve()
        try:
            matcher = SherwinWilliamsMatcher(source)
            data_folder = Path(__file__).resolve().parent.parent / "data"
            target = data_folder / source.name
            if source != target.resolve():
                if target.exists():
                    target = data_folder / f"{source.stem}_imported.json"
                shutil.copy2(source, target)
            self.catalogs[matcher.catalog_name] = target
            if self.paint_company.findText(matcher.catalog_name) < 0:
                self.paint_company.addItem(matcher.catalog_name)
            self.paint_company.setCurrentText(matcher.catalog_name)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Catalog import failed", str(error))

    def set_palette(
        self,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        paint_plan: SherwinWilliamsPaintPlan | None = None,
    ) -> None:
        estimator = self.paint_estimator()
        if paint_plan is None:
            paint_plan = self.create_paint_plan(palette, color_counts)
        self.palette_panel.set_palette(
            palette,
            color_counts,
            estimator,
            paint_plan,
        )
        self.summary_panel.set_plan(paint_plan)
        self.setCurrentWidget(self.summary_panel)

    def paint_estimator(self) -> PaintUsageEstimator:
        return PaintUsageEstimator(
            coverage_sq_ft_per_gallon=self.paint_coverage.value(),
            process_factor=self.paint_process_factor.value(),
            tile_surface_area_sq_in=self.tile_surface_area.value(),
        )

    def create_paint_plan(
        self,
        palette: Mapping[int, RGB],
        color_counts: Mapping[int, int],
        positions_by_palette: Mapping[int, list[tuple[int, int]]] | None = None,
    ) -> SherwinWilliamsPaintPlan:
        return SherwinWilliamsPaintPlan.build(
            palette,
            color_counts,
            self.matcher,
            self.paint_estimator(),
            self.paint_price.value(),
            target_color_count=self.sw_colors.value(),
            positions_by_palette=positions_by_palette,
            override_codes=self.paint_overrides,
        )

    def set_pages(self, sections: list[PageSection]) -> None:
        self.pages_panel.set_sections(sections)
