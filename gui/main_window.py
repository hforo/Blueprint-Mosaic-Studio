"""Application window coordinating editor widgets and the render pipeline."""

from __future__ import annotations

from math import ceil
from pathlib import Path
from collections import Counter
from tempfile import gettempdir

from PySide6.QtCore import (
    QObject, QPoint, QPointF, QRectF, QRunnable, QSettings, QStandardPaths, Qt, QThreadPool, QTimer,
    Signal, Slot,
)
from PySide6.QtGui import QAction, QImage, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QProgressDialog,
)
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QWidget
from PySide6.QtWidgets import QToolTip

from config import (
    BORDER, CELL_SIZE, PAGE_CELL_SIZE, PAGE_COLUMNS, PAGE_ROWS,
    PAGE_TITLE_HEIGHT,
)
from PIL import Image as PILImage, ImageDraw as PILImageDraw
from image import prepare_mosaic_image, process_image
from pages import OVERVIEW_SIZE, render_pages
from render import (
    blueprint_output_path, draw_tile_fill, mosaic_background_rgb, render_master,
)
from project_io import load_project, save_project
from export import export_blueprint_pdf, export_shopping_csv

from .canvas import CanvasView
from .sidebar import Sidebar


class PreviewSignals(QObject):
    ready = Signal(int, bytes, int, int, int, int)


class PreviewWorker(QRunnable):
    """Prepare one preview away from the GUI thread."""

    def __init__(
        self, request_id: int, image_path: str, width: int, height: int,
        colors: int, dither: str, crop_box: tuple[int, int, int, int],
        tile_type: str, background_name: str,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.image_path = image_path
        self.width = width
        self.height = height
        self.colors = colors
        self.dither = dither
        self.crop_box = crop_box
        self.tile_type = tile_type
        self.background_name = background_name
        self.signals = PreviewSignals()

    def run(self) -> None:
        try:
            _, _, palette_image = prepare_mosaic_image(
                self.image_path, self.width, self.height, self.colors,
                self.dither, self.crop_box,
            )
            source = palette_image.convert("RGB")
            scale = max(1, min(24, 1200 // max(source.size)))
            shaped = self.tile_type in (
                "Round disc — one face",
                "Sphere — all surface",
                "4-piece 5.56 cartridge tile",
            )
            if shaped:
                scale = max(4, scale)
                mosaic = PILImage.new(
                    "RGB", (source.width * scale, source.height * scale),
                    mosaic_background_rgb(self.background_name),
                )
                draw = PILImageDraw.Draw(mosaic)
                pixels = source.load()
                for row in range(source.height):
                    for column in range(source.width):
                        draw_tile_fill(
                            draw, column * scale, row * scale, scale,
                            pixels[column, row], self.tile_type,
                        )
            else:
                mosaic = source.resize(
                    (source.width * scale, source.height * scale),
                    PILImage.Resampling.NEAREST,
                )
            PILImageDraw.Draw(mosaic).rectangle(
                (0, 0, mosaic.width - 1, mosaic.height - 1),
                outline="black",
                width=max(1, scale // 8),
            )
        except (OSError, ValueError):
            return
        self.signals.ready.emit(
            self.request_id, mosaic.tobytes(), mosaic.width, mosaic.height,
            self.width, self.height,
        )


class PaintTileCommand(QUndoCommand):
    def __init__(
        self, window: "MainWindow", row: int, column: int,
        old_color: int, new_color: int,
    ) -> None:
        super().__init__(f"Repaint {column + 1},{row + 1}")
        self.window = window
        self.row = row
        self.column = column
        self.old_color = old_color
        self.new_color = new_color

    def redo(self) -> None:
        self.window._apply_tile_color(
            self.row, self.column, self.new_color, refresh=True,
        )

    def undo(self) -> None:
        self.window._apply_tile_color(
            self.row, self.column, self.old_color, refresh=True,
        )


class MainWindow(QMainWindow):
    """Top-level application shell; domain behavior lives in dedicated modules."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Blueprint Mosaic Studio")
        self.resize(1600, 900)
        self._sherwin_preview_path: Path | None = None
        self._sherwin_preview_source: str | None = None
        self._active_project = None
        self._active_paint_plan = None
        self._page_sections = []
        self._active_page_section = None
        self._numbered_preview_path: Path | None = None
        self._paint_numbered_preview_path: Path | None = None
        self._project_path: Path | None = None
        self._blueprint_stale = True
        self._sizing_sync = False
        self._preview_request_id = 0
        self._preview_worker: PreviewWorker | None = None
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(1)
        self.undo_stack = QUndoStack(self)
        self._last_hovered_cell: tuple[int, int] | None = None
        self._live_preview_timer = QTimer(self)
        self._live_preview_timer.setSingleShot(True)
        self._live_preview_timer.setInterval(180)
        self._live_preview_timer.timeout.connect(self._update_live_mosaic_preview)
        self._settings = QSettings()
        autosave_folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        try:
            autosave_folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            autosave_folder = Path(gettempdir()) / "BlueprintMosaicStudio"
            autosave_folder.mkdir(parents=True, exist_ok=True)
        self._autosave_path = autosave_folder / "autosave.bms.json"
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._autosave_project)
        self._autosave_timer.start()
        self.canvas = CanvasView(self)
        self.sidebar = Sidebar(self)
        self._build_central_widget()
        self._build_status_bar()
        self._build_menu()
        self._connect_signals()

    def _build_central_widget(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(central)

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        self.message_label = QLabel(
            "Open or drop an image, then generate the blueprint to unlock the result tabs"
        )
        self.zoom_label = QLabel("Zoom: —")
        self.image_label = QLabel("Image: —")
        self.crop_label = QLabel("Crop: —")
        self.mouse_label = QLabel("Cursor: —")
        status_bar.addWidget(self.message_label, 1)
        for label in (self.zoom_label, self.image_label,
                      self.crop_label, self.mouse_label):
            label.setMinimumWidth(115)
            status_bar.addPermanentWidget(label)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        open_action = QAction("&Open Image…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_image)
        file_menu.addAction(open_action)
        open_project_action = QAction("Open &Project…", self)
        open_project_action.setShortcut("Ctrl+Shift+O")
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)
        save_project_action = QAction("&Save Project…", self)
        save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        self.recover_action = QAction("Recover &Autosave", self)
        self.recover_action.setEnabled(self._autosave_path.exists())
        self.recover_action.triggered.connect(lambda: self.open_project(str(self._autosave_path)))
        file_menu.addAction(self.recover_action)
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_projects()
        generate_action = QAction("Generate &Blueprint", self)
        generate_action.setShortcut("Ctrl+G")
        generate_action.triggered.connect(self.generate_blueprint)
        file_menu.addAction(generate_action)
        file_menu.addSeparator()
        export_pdf_action = QAction("Export Blueprint &PDF…", self)
        export_pdf_action.triggered.connect(self.export_blueprint_pdf)
        file_menu.addAction(export_pdf_action)
        export_csv_action = QAction("Export Paint Shopping &List…", self)
        export_csv_action.triggered.connect(self.export_shopping_list)
        file_menu.addAction(export_csv_action)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = self.menuBar().addMenu("&View")
        fit_action = QAction("&Fit to Window", self)
        fit_action.setShortcut("Ctrl+0")
        fit_action.triggered.connect(self.canvas.fit_to_window)
        view_menu.addAction(fit_action)
        reset_action = QAction("&Actual Size (100%)", self)
        reset_action.setShortcut("Ctrl+1")
        reset_action.triggered.connect(self.canvas.reset_zoom)
        view_menu.addAction(reset_action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_stack.createUndoAction(self, "&Undo"))
        edit_menu.addAction(self.undo_stack.createRedoAction(self, "&Redo"))

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        self.sidebar.generate.clicked.connect(self.generate_blueprint)
        self.sidebar.generate_pdf.clicked.connect(self.export_blueprint_pdf)
        self.canvas.zoom_changed.connect(self._update_zoom_status)
        self.canvas.image_changed.connect(self._update_image_status)
        self.canvas.crop_changed.connect(self._update_crop_status)
        self.canvas.mouse_position_changed.connect(self._update_mouse_status)
        self.canvas.image_clicked.connect(self._select_summary_color_at)
        self.canvas.image_load_failed.connect(self._show_load_error)
        self.sidebar.pages_panel.page_selected.connect(self._show_page_preview)
        self.sidebar.pages_panel.source_requested.connect(
            self._restore_source_image
        )
        self.sidebar.pages_panel.previous_requested.connect(
            lambda: self._navigate_page(-1)
        )
        self.sidebar.pages_panel.next_requested.connect(
            lambda: self._navigate_page(1)
        )
        self.sidebar.currentChanged.connect(self._on_sidebar_tab_changed)
        self.sidebar.summary_panel.color_selected.connect(
            self._highlight_summary_color
        )
        self.sidebar.palette_panel.color_selected.connect(
            self._highlight_summary_color
        )
        self.sidebar.grid.valueChanged.connect(self._schedule_live_preview)
        self.sidebar.image_colors.valueChanged.connect(self._schedule_live_preview)
        self.sidebar.image_colors.valueChanged.connect(self._update_project_statistics)
        self.sidebar.sw_colors.valueChanged.connect(self._update_project_statistics)
        self.sidebar.dither.currentTextChanged.connect(self._schedule_live_preview)
        self.sidebar.tile_type.currentTextChanged.connect(self._schedule_live_preview)
        self.sidebar.background_color.currentTextChanged.connect(
            self._schedule_live_preview
        )
        self.sidebar.live_preview.toggled.connect(self._toggle_live_preview)
        self.sidebar.grid.valueChanged.connect(self._sync_finished_width)
        self.sidebar.tile_size.valueChanged.connect(self._sync_finished_width)
        self.sidebar.finished_width.valueChanged.connect(self._sync_grid_width)
        self.sidebar.size_mode.currentIndexChanged.connect(self._on_size_mode_changed)
        self.sidebar.preview_mode.currentTextChanged.connect(self._show_preview_mode)
        self.sidebar.paint_company.currentTextChanged.connect(
            self._on_paint_company_changed
        )
        self.sidebar.palette_panel.paint_override_requested.connect(
            self._choose_paint_override
        )
        self.sidebar.palette_panel.paint_unlock_requested.connect(
            self._unlock_paint_overrides
        )
        self.sidebar.palette_panel.merge_requested.connect(self._merge_palette_colors)
        for signal in (
            self.sidebar.grid.valueChanged,
            self.sidebar.tile_size.valueChanged,
            self.sidebar.tile_type.currentTextChanged,
            self.sidebar.background_color.currentTextChanged,
            self.sidebar.tile_surface_area.valueChanged,
            self.sidebar.image_colors.valueChanged,
            self.sidebar.sw_colors.valueChanged,
            self.sidebar.dither.currentTextChanged,
            self.sidebar.paint_coverage.valueChanged,
            self.sidebar.paint_process_factor.valueChanged,
            self.sidebar.paint_price.valueChanged,
        ):
            signal.connect(self._mark_blueprint_stale)

    @Slot()
    def _mark_blueprint_stale(self) -> None:
        if self._active_project is None:
            self.sidebar.settings_panel.generation_status.setText(
                "Blueprint not generated"
            )
            return
        self._blueprint_stale = True
        self.sidebar.setCurrentWidget(self.sidebar.settings_panel)
        self.sidebar.set_result_tabs_enabled(False)
        self.sidebar.settings_panel.generation_status.setText(
            "Blueprint out of date — generate again to apply changed settings"
        )

    def _set_blueprint_current(self, catalog_name: str) -> None:
        self._blueprint_stale = False
        self.sidebar.settings_panel.generation_status.setText(
            f"Blueprint current — {catalog_name}"
        )

    @Slot()
    def open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)",
        )
        if filename:
            if self.canvas.load_image(filename):
                self._sherwin_preview_path = None
                self._sherwin_preview_source = None
                self._active_project = None
                self._active_paint_plan = None
                self._page_sections = []
                self._active_page_section = None
                self._numbered_preview_path = None
                self._paint_numbered_preview_path = None
                self.sidebar.setCurrentWidget(self.sidebar.settings_panel)
                self.sidebar.set_result_tabs_enabled(False)
                self.sidebar.settings_panel.generation_status.setText(
                    "Blueprint not generated"
                )
                self._update_project_statistics()
                self._schedule_live_preview()

    @Slot()
    def save_project(self) -> None:
        source_path = self.canvas.source_image_path
        if source_path is None:
            QMessageBox.information(self, "No project", "Open an image first.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Project",
            str(self._project_path or Path(source_path).with_suffix(".bms.json")),
            "Blueprint Mosaic Studio (*.bms.json)",
        )
        if not filename:
            return
        payload = self._project_payload()
        if payload is None:
            return
        try:
            save_project(filename, payload)
        except OSError as error:
            QMessageBox.critical(self, "Save failed", str(error))
            return
        self._project_path = Path(filename)
        self._remember_recent_project(self._project_path)
        self.message_label.setText(f"Saved project {self._project_path.name}")

    def _project_payload(self) -> dict | None:
        source_path = self.canvas.source_image_path
        if source_path is None:
            return None
        crop = self.canvas.source_crop_rect()
        return {
            "source_path": str(Path(source_path).resolve()),
            "crop": [crop.left(), crop.top(), crop.right(), crop.bottom()],
            "settings": {
                "grid": self.sidebar.grid.value(),
                "paint_company": self.sidebar.paint_company.currentText(),
                "size_mode": self.sidebar.size_mode.currentIndex(),
                "finished_width": self.sidebar.finished_width.value(),
                "tile_size": self.sidebar.tile_size.value(),
                "tile_type": self.sidebar.tile_type.currentText(),
                "background_color": self.sidebar.background_color.currentText(),
                "tile_surface_area": self.sidebar.tile_surface_area.value(),
                "image_colors": self.sidebar.image_colors.value(),
                "sw_colors": self.sidebar.sw_colors.value(),
                "dither": self.sidebar.dither.currentText(),
                "paint_coverage": self.sidebar.paint_coverage.value(),
                "process_factor": self.sidebar.paint_process_factor.value(),
                "paint_price": self.sidebar.paint_price.value(),
            },
            "paint_overrides": self.sidebar.paint_overrides,
            "grid_colors": (
                [[cell.color for cell in row] for row in self._active_project.grid]
                if self._active_project is not None else None
            ),
            "last_page_index": self.sidebar.pages_panel.page_list.currentRow(),
        }

    def _autosave_project(self) -> None:
        payload = self._project_payload()
        if payload is None:
            return
        try:
            save_project(self._autosave_path, payload)
        except OSError:
            pass
        else:
            self.recover_action.setEnabled(True)

    def _remember_recent_project(self, path: Path) -> None:
        resolved = str(path.resolve())
        recent = [str(value) for value in self._settings.value("recentProjects", [], list)]
        recent = [value for value in recent if value != resolved]
        self._settings.setValue("recentProjects", [resolved, *recent][:8])
        self._refresh_recent_projects()

    def _refresh_recent_projects(self) -> None:
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        recent = [str(value) for value in self._settings.value("recentProjects", [], list)]
        existing = [path for path in recent if Path(path).exists()]
        self.recent_menu.setEnabled(bool(existing))
        for path in existing:
            action = self.recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, value=path: self.open_project(value))

    def open_project(self, filename: str | None = None) -> None:
        if not filename:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Open Project", "",
                "Blueprint Mosaic Studio (*.bms.json);;JSON (*.json)",
            )
            if not filename:
                return
        try:
            document = load_project(filename)
            source_path = Path(document["source_path"])
            if not source_path.exists():
                raise ValueError(f"Source image no longer exists: {source_path}")
            if not self.canvas.load_image(source_path):
                return
            self._active_project = None
            self._active_paint_plan = None
            settings = document.get("settings", {})
            self.sidebar.live_preview.setChecked(False)
            paint_company = str(settings.get("paint_company", ""))
            if self.sidebar.paint_company.findText(paint_company) >= 0:
                self.sidebar.paint_company.setCurrentText(paint_company)
            self.sidebar.grid.setValue(int(settings.get("grid", 96)))
            self.sidebar.tile_size.setValue(float(settings.get("tile_size", 0.75)))
            saved_tile_type = str(settings.get("tile_type", "Custom coated area"))
            if self.sidebar.tile_type.findText(saved_tile_type) >= 0:
                self.sidebar.tile_type.setCurrentText(saved_tile_type)
            if saved_tile_type == "Custom coated area":
                self.sidebar.tile_surface_area.setValue(float(
                    settings.get(
                        "tile_surface_area",
                        float(settings.get("tile_size", 0.75)) ** 2,
                    )
                ))
            else:
                self.sidebar.settings_panel._apply_tile_type_preset()
            saved_background = str(settings.get("background_color", "White"))
            if self.sidebar.background_color.findText(saved_background) >= 0:
                self.sidebar.background_color.setCurrentText(saved_background)
            self.sidebar.image_colors.setValue(int(settings.get("image_colors", 256)))
            self.sidebar.sw_colors.setValue(int(settings.get("sw_colors", 100)))
            self.sidebar.dither.setCurrentText(str(settings.get("dither", "None")))
            self.sidebar.paint_coverage.setValue(float(settings.get("paint_coverage", 350)))
            self.sidebar.paint_process_factor.setValue(float(settings.get("process_factor", 2)))
            self.sidebar.paint_price.setValue(float(settings.get("paint_price", 64)))
            self.sidebar.size_mode.setCurrentIndex(int(settings.get("size_mode", 0)))
            self.sidebar.finished_width.setValue(float(settings.get("finished_width", 72)))
            crop = document.get("crop")
            if crop and self.canvas.crop_item is not None:
                left, top, right, bottom = map(float, crop)
                self.canvas.crop_item.set_crop_rect(
                    QRectF(left, top, right - left, bottom - top)
                )
            self.sidebar.paint_overrides = {
                int(key): str(value)
                for key, value in document.get("paint_overrides", {}).items()
            }
            self.generate_blueprint()
            saved_grid = document.get("grid_colors")
            if self._active_project is not None and saved_grid:
                counts: Counter[int] = Counter()
                for row_index, saved_row in enumerate(saved_grid):
                    if row_index >= self._active_project.height:
                        break
                    for column, color in enumerate(saved_row):
                        if column >= self._active_project.width:
                            break
                        color = int(color)
                        if color not in self._active_project.palette:
                            continue
                        cell = self._active_project.grid[row_index][column]
                        cell.color = color
                        cell.rgb = self._active_project.palette[color]
                        counts[color] += 1
                self._active_project.color_counts = dict(counts)
                self._rebuild_paint_plan(switch_tab=False)
                self._render_edited_preview()
            self._project_path = Path(filename)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Open project failed", str(error))
            return
        self.undo_stack.clear()
        if self._project_path != self._autosave_path:
            self._remember_recent_project(self._project_path)
        page_index = int(document.get("last_page_index", -1))
        if 0 <= page_index < self.sidebar.pages_panel.page_list.count():
            page_list = self.sidebar.pages_panel.page_list
            page_list.blockSignals(True)
            page_list.setCurrentRow(page_index)
            page_list.blockSignals(False)
        self.message_label.setText(f"Opened project {Path(filename).name}")

    def _grid_dimensions(self) -> tuple[int, int]:
        width = self.sidebar.grid.value()
        crop = self.canvas.source_crop_rect()
        height = (
            max(1, round(width * crop.height() / crop.width()))
            if not crop.isEmpty() else width
        )
        return width, height

    @Slot()
    def _sync_finished_width(self) -> None:
        if self._sizing_sync:
            return
        self._sizing_sync = True
        self.sidebar.finished_width.setValue(
            self.sidebar.grid.value() * self.sidebar.tile_size.value()
        )
        self._sizing_sync = False
        self._update_project_statistics()

    @Slot()
    def _sync_grid_width(self) -> None:
        if self._sizing_sync or self.sidebar.size_mode.currentIndex() != 1:
            return
        self._sizing_sync = True
        columns = round(
            self.sidebar.finished_width.value() / self.sidebar.tile_size.value()
        )
        self.sidebar.grid.setValue(max(8, min(500, columns)))
        self._sizing_sync = False
        self._update_project_statistics()
        self._schedule_live_preview()

    @Slot()
    def _on_size_mode_changed(self) -> None:
        by_finished_size = self.sidebar.size_mode.currentIndex() == 1
        self.sidebar.grid.setEnabled(not by_finished_size)
        self.sidebar.finished_width.setEnabled(by_finished_size)
        if by_finished_size:
            self._sync_grid_width()
        else:
            self._sync_finished_width()

    def _update_project_statistics(self) -> None:
        if self.canvas.source_image_path is None:
            self.sidebar.statistics.setText(
                "Open an image to calculate mosaic dimensions."
            )
            return
        width, height = self._grid_dimensions()
        tile = self.sidebar.tile_size.value()
        colors = min(self.sidebar.image_colors.value(), width * height)
        self.sidebar.statistics.setText(
            f"{width} x {height} grid · {width * height:,} squares\n"
            f"Finished size: {width * tile:.2f} x {height * tile:.2f} in\n"
            f"Up to {colors} image colors · "
            f"{self.sidebar.sw_colors.value()} requested paints"
        )

    @Slot()
    def _schedule_live_preview(self) -> None:
        if (
            self.sidebar.live_preview.isChecked()
            and self.sidebar.currentWidget() is self.sidebar.settings_panel
        ):
            self._live_preview_timer.start()

    @Slot(bool)
    def _toggle_live_preview(self, enabled: bool) -> None:
        if enabled:
            self._schedule_live_preview()
        else:
            self._live_preview_timer.stop()
            self._preview_request_id += 1
            if self._preview_worker is not None:
                try:
                    self._preview_pool.tryTake(self._preview_worker)
                except RuntimeError:
                    pass
                self._preview_worker = None
            if self.canvas.restore_source_image():
                self.message_label.setText("Source image ready for crop editing")

    @Slot()
    def _update_live_mosaic_preview(self) -> None:
        if (
            not self.sidebar.live_preview.isChecked()
            or self.sidebar.currentWidget() is not self.sidebar.settings_panel
        ):
            return
        image_path = self.canvas.source_image_path
        crop = self.canvas.source_crop_rect()
        if image_path is None or crop.isEmpty():
            return
        grid_width = self.sidebar.grid.value()
        grid_height = max(1, round(grid_width * crop.height() / crop.width()))
        crop_box = (
            int(crop.left()), int(crop.top()),
            int(ceil(crop.right())), int(ceil(crop.bottom())),
        )
        self._preview_request_id += 1
        if self._preview_worker is not None:
            try:
                self._preview_pool.tryTake(self._preview_worker)
            except RuntimeError:
                pass
            self._preview_worker = None
        worker = PreviewWorker(
            self._preview_request_id, image_path, grid_width, grid_height,
            self.sidebar.image_colors.value(),
            self.sidebar.dither.currentText().lower(), crop_box,
            self.sidebar.tile_type.currentText(),
            self.sidebar.background_color.currentText(),
        )
        worker.signals.ready.connect(self._apply_live_preview)
        self._preview_worker = worker
        self.message_label.setText("Updating live mosaic preview…")
        self._preview_pool.start(worker)

    @Slot(int, bytes, int, int, int, int)
    def _apply_live_preview(
        self, request_id: int, pixels: bytes, image_width: int,
        image_height: int, grid_width: int, grid_height: int,
    ) -> None:
        if (
            request_id != self._preview_request_id
            or not self.sidebar.live_preview.isChecked()
        ):
            return
        self._preview_worker = None
        image = QImage(
            pixels, image_width, image_height, image_width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
        if self.canvas.show_live_preview(image):
            self.message_label.setText(
                f"Live mosaic preview: {grid_width} × {grid_height} squares"
            )
            self._update_project_statistics()

    @Slot()
    def generate_blueprint(self) -> None:
        """Run the established image, master, and printable-page pipeline."""
        image_path = self.canvas.source_image_path
        if image_path is None:
            QMessageBox.information(self, "No image", "Open an image first.")
            return
        crop = self.canvas.source_crop_rect()
        grid_width = self.sidebar.grid.value()
        grid_height = max(1, round(grid_width * crop.height() / crop.width()))
        crop_box = (int(crop.left()), int(crop.top()),
                    int(ceil(crop.right())), int(ceil(crop.bottom())))
        paint_company = self.sidebar.matcher.catalog_name
        warnings = self._preflight_warnings(grid_width, grid_height)
        if warnings:
            response = QMessageBox.warning(
                self,
                "Blueprint Preflight",
                "Please review these items before generation:\n\n• "
                + "\n• ".join(warnings)
                + "\n\nGenerate anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

        progress = QProgressDialog(
            "Preparing source image...", "", 0, 8, self,
        )
        progress.setWindowTitle("Generating Blueprint")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setValue(0)
        progress.show()

        def advance(step: int, message: str) -> None:
            progress.setLabelText(message)
            progress.setValue(step)
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.message_label.setText("Generating blueprint…")
        QApplication.processEvents()
        try:
            advance(0, "Averaging source image into mosaic grid cells...")
            project = process_image(
                Path(image_path), grid_width, grid_height,
                self.sidebar.colors.value(),
                dither=self.sidebar.dither.currentText().lower(), crop_box=crop_box,
                tile_size_inches=self.sidebar.tile_size.value(),
                tile_type=self.sidebar.tile_type.currentText(),
                background_name=self.sidebar.background_color.currentText(),
            )
            advance(1, "Matching the mosaic palette to paint colors...")
            positions_by_palette: dict[int, list[tuple[int, int]]] = {}
            for project_row in project.grid:
                for cell in project_row:
                    positions_by_palette.setdefault(cell.color, []).append(
                        (cell.row, cell.column)
                    )
            paint_plan = self.sidebar.create_paint_plan(
                project.palette,
                project.color_counts,
                positions_by_palette,
            )
            advance(2, "Rendering numbered image-color blueprint...")
            render_master(
                project,
                filename_tag="OriginalColors_Numbered",
                title_suffix="Original Colors — Numbered Blueprint",
            )
            self._numbered_preview_path = blueprint_output_path(
                project,
                filename_tag="OriginalColors_Numbered",
            ).resolve()
            advance(3, "Rendering clean image-color blueprint...")
            render_master(
                project,
                filename_tag="OriginalColors_NoCellLabels",
                title_suffix="Original Colors — No Cell Labels",
                show_labels=False,
                show_grid=False,
            )
            advance(4, f"Rendering numbered {paint_company} blueprint...")
            render_master(
                project,
                color_overrides=paint_plan.color_overrides,
                label_overrides=paint_plan.blueprint_labels,
                filename_tag="SherwinWilliams_Numbered",
                palette_color_count=len(paint_plan.rows),
                title_suffix=f"{paint_company} — Numbered Blueprint",
            )
            self._paint_numbered_preview_path = blueprint_output_path(
                project,
                color_count=len(paint_plan.rows),
                filename_tag="SherwinWilliams_Numbered",
            ).resolve()
            advance(5, f"Rendering clean {paint_company} blueprint...")
            render_master(
                project,
                color_overrides=paint_plan.color_overrides,
                filename_tag="SherwinWilliams_NoCellLabels",
                palette_color_count=len(paint_plan.rows),
                title_suffix=f"{paint_company} — No Cell Labels",
                show_labels=False,
                show_grid=False,
            )
            self._sherwin_preview_path = blueprint_output_path(
                project,
                color_count=len(paint_plan.rows),
                filename_tag="SherwinWilliams_NoCellLabels",
            ).resolve()
            self._sherwin_preview_source = str(Path(image_path).resolve())
            advance(6, "Creating printable detail pages...")
            page_sections = render_pages(
                project,
                color_overrides=paint_plan.color_overrides,
                label_overrides=paint_plan.blueprint_labels,
                color_label=f"{paint_company} Build Page",
            )
            advance(7, "Updating summaries and page navigation...")
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Generation failed", str(error))
            self.message_label.setText("Blueprint generation failed")
        else:
            self._active_project = project
            self._active_paint_plan = paint_plan
            self._page_sections = page_sections
            self.sidebar.set_result_tabs_enabled(True)
            self.sidebar.set_palette(
                project.palette,
                project.color_counts,
                paint_plan,
            )
            self.sidebar.set_pages(page_sections)
            self._set_blueprint_current(paint_company)
            advance(8, "Blueprint generation complete")
            self.message_label.setText(
                "Original and Sherwin-Williams labeled/unlabeled blueprints generated"
            )
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()

    def _preflight_warnings(self, width: int, height: int) -> list[str]:
        warnings = []
        page_count = ceil(width / PAGE_COLUMNS) * ceil(height / PAGE_ROWS)
        if self.sidebar.tile_size.value() < 0.25:
            warnings.append("Tile size is below 0.25 in and may be difficult to build.")
        if page_count > 100:
            warnings.append(f"This grid will create {page_count:,} detail pages.")
        if self.sidebar.sw_colors.value() > self.sidebar.image_colors.value():
            warnings.append("Requested paint colors exceed the image-color limit.")
        if self.sidebar.image_colors.value() > width * height:
            warnings.append("Image-color limit exceeds the number of mosaic squares.")
        return warnings

    @Slot()
    def export_shopping_list(self) -> None:
        if self._active_paint_plan is None:
            QMessageBox.information(self, "Generate Blueprint", "Generate a blueprint before exporting a shopping list.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Paint Shopping List", "paint-shopping-list.csv",
            "CSV spreadsheet (*.csv)",
        )
        if not filename:
            return
        try:
            export_shopping_csv(filename, self._active_paint_plan)
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        self.message_label.setText(f"Exported shopping list to {Path(filename).name}")

    @Slot()
    def export_blueprint_pdf(self) -> None:
        if (
            self._active_project is None
            or self._active_paint_plan is None
            or self._paint_numbered_preview_path is None
        ):
            QMessageBox.information(self, "Generate Blueprint", "Generate a blueprint before exporting a PDF.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Blueprint PDF", "blueprint-package.pdf",
            "PDF document (*.pdf)",
        )
        if not filename:
            return
        try:
            export_blueprint_pdf(
                filename, self._paint_numbered_preview_path,
                [section.image_path for section in self._page_sections],
                self._active_paint_plan,
                self._active_project.source_path.name if self._active_project.source_path else "Blueprint",
                self._active_project,
            )
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        self.message_label.setText(f"Exported blueprint package to {Path(filename).name}")

    def _navigate_page(self, offset: int) -> None:
        page_list = self.sidebar.pages_panel.page_list
        if not self._page_sections:
            return
        current = page_list.currentRow()
        target = min(max((current if current >= 0 else 0) + offset, 0), len(self._page_sections) - 1)
        self.sidebar.pages_panel.select_page(self._page_sections[target].image_path)

    @Slot(float)
    def _update_zoom_status(self, percentage: float) -> None:
        self.zoom_label.setText(f"Zoom: {percentage:.0f}%")

    @Slot(str, int, int)
    def _update_image_status(self, path: str, width: int, height: int) -> None:
        self.image_label.setText(f"Image: {width} × {height} px")
        self.message_label.setText(f"Loaded {Path(path).name}")

    @Slot(QRectF)
    def _update_crop_status(self, rect: QRectF) -> None:
        if rect.isEmpty():
            self.crop_label.setText("Crop: preview")
        else:
            self.crop_label.setText(
                f"Crop: {round(rect.width())} × {round(rect.height())} px"
            )

        self._update_project_statistics()

    @Slot(QPointF)
    def _update_mouse_status(self, position: QPointF) -> None:
        if self._is_detail_overview_position(position):
            self.canvas.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self.canvas.viewport().setToolTip(
                "Click the miniature mosaic to open the corresponding detail page."
            )
            self.mouse_label.setText("Click overview to open its detail page")
            return
        self.canvas.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.canvas.viewport().setToolTip("")
        if self._show_summary_cell_hover(position):
            return
        self._clear_cell_hover()
        if self.canvas.model.image_rect.contains(position):
            self.mouse_label.setText(
                f"Cursor: {int(position.x())}, {int(position.y())}"
            )
        else:
            self.mouse_label.setText("Cursor: —")

    def _is_detail_overview_position(self, position: QPointF) -> bool:
        section = self._active_page_section
        if (
            section is None
            or self.sidebar.currentWidget() is not self.sidebar.pages_panel
            or self.canvas.model.image_path is None
            or Path(self.canvas.model.image_path).resolve()
            != section.image_path.resolve()
        ):
            return False
        detail_columns = section.end_column - section.start_column
        overview_left = (
            detail_columns * PAGE_CELL_SIZE + PAGE_TITLE_HEIGHT * 2 + 24
        )
        overview_width, overview_height = OVERVIEW_SIZE
        return (
            overview_left <= position.x() < overview_left + overview_width
            and 62 <= position.y() < 62 + overview_height
        )

    def _show_summary_cell_hover(self, position: QPointF) -> bool:
        if (
            self.sidebar.currentWidget() is not self.sidebar.summary_panel
            or self._active_project is None
            or self._active_paint_plan is None
        ):
            return False
        column = int((position.x() - BORDER) // CELL_SIZE)
        row = int((position.y() - BORDER) // CELL_SIZE)
        if not (
            0 <= row < self._active_project.height
            and 0 <= column < self._active_project.width
        ):
            return False

        cell = self._active_project.grid[row][column]
        match = self._active_paint_plan.matches.get(cell.color)
        if match is None:
            return False
        plan_row = next(
            (
                item
                for item in self._active_paint_plan.rows
                if item.paint.code == match.color.code
            ),
            None,
        )
        usage = ""
        if plan_row is not None:
            estimate_text = plan_row.estimate.display_text().replace("\n", " · ")
            usage = (
                f"\nUsed by {plan_row.tile_count:,} squares"
                f"\nEstimated paint: {estimate_text}"
            )
        tooltip = (
            f"Coordinate: {cell.coordinate}\n"
            f"Mosaic color: #{cell.color}\n"
            f"{match.color.display_code} · {match.color.name}\n"
            f"{match.color.hex_value} · "
            f"RGB {match.color.rgb[0]}, {match.color.rgb[1]}, "
            f"{match.color.rgb[2]}{usage}"
        )
        self.mouse_label.setText(
            f"{cell.coordinate} · {match.color.display_code} "
            f"{match.color.name}"
        )
        hovered_cell = (row, column)
        if hovered_cell != self._last_hovered_cell:
            viewport_point = self.canvas.mapFromScene(position) + QPoint(14, 18)
            QToolTip.showText(
                self.canvas.viewport().mapToGlobal(viewport_point),
                tooltip,
                self.canvas.viewport(),
            )
            self._last_hovered_cell = hovered_cell
        return True

    def _clear_cell_hover(self) -> None:
        if self._last_hovered_cell is not None:
            QToolTip.hideText()
            self._last_hovered_cell = None

    @Slot(QPointF)
    def _select_summary_color_at(self, position: QPointF) -> None:
        """Select the summary paint row represented by a clicked mosaic cell."""
        if (
            self._active_project is None
            or self.canvas.model.image_path is None
        ):
            return
        displayed_path = Path(self.canvas.model.image_path).resolve()
        on_master = (
            self._sherwin_preview_path is not None
            and displayed_path == self._sherwin_preview_path.resolve()
        )
        on_page = (
            self._active_page_section is not None
            and displayed_path == self._active_page_section.image_path.resolve()
        )
        if (
            on_page
            and self.sidebar.currentWidget() is self.sidebar.pages_panel
        ):
            self._open_page_from_detail_overview(position)
            return
        on_source = (
            self._sherwin_preview_source is not None
            and displayed_path == Path(self._sherwin_preview_source).resolve()
        )
        if on_master:
            column = int((position.x() - BORDER) // CELL_SIZE)
            row = int((position.y() - BORDER) // CELL_SIZE)
        elif (
            on_source
            and self.sidebar.currentWidget() is self.sidebar.pages_panel
        ):
            crop = self.canvas.source_crop_rect()
            if crop.isEmpty() or not crop.contains(position):
                return
            column = int(
                (position.x() - crop.left())
                / crop.width()
                * self._active_project.width
            )
            row = int(
                (position.y() - crop.top())
                / crop.height()
                * self._active_project.height
            )
        elif on_page:
            local_column = int(
                (position.x() - PAGE_TITLE_HEIGHT) // PAGE_CELL_SIZE
            )
            local_row = int(
                (position.y() - PAGE_TITLE_HEIGHT) // PAGE_CELL_SIZE
            )
            page_width = (
                self._active_page_section.end_column
                - self._active_page_section.start_column
            )
            page_height = (
                self._active_page_section.end_row
                - self._active_page_section.start_row
            )
            if not (
                0 <= local_row < page_height
                and 0 <= local_column < page_width
            ):
                return
            column = self._active_page_section.start_column + local_column
            row = self._active_page_section.start_row + local_row
        else:
            return
        if not (
            0 <= row < self._active_project.height
            and 0 <= column < self._active_project.width
        ):
            return
        if (
            self.sidebar.currentWidget() is self.sidebar.pages_panel
            and (on_master or on_source)
        ):
            self._select_page_for_cell(row, column)
            return
        palette_number = self._active_project.grid[row][column].color
        if on_master and self.sidebar.palette_panel.edit_tiles.isChecked():
            selected = self.sidebar.palette_panel.selected_palette_numbers()
            if selected and selected[0] != palette_number:
                self.undo_stack.push(
                    PaintTileCommand(
                        self, row, column, palette_number, selected[0],
                    )
                )
            return
        if self.sidebar.summary_panel.select_palette_number(palette_number):
            self.sidebar.setCurrentWidget(self.sidebar.summary_panel)
            self._highlight_summary_color(
                self.sidebar.summary_panel.selected_palette_numbers()
            )

    def _open_page_from_detail_overview(self, position: QPointF) -> None:
        """Open the page represented by a click in a detail page's overview."""
        section = self._active_page_section
        project = self._active_project
        if section is None or project is None:
            return
        detail_columns = section.end_column - section.start_column
        detail_grid_width = (
            detail_columns * PAGE_CELL_SIZE + PAGE_TITLE_HEIGHT * 2
        )
        overview_left = detail_grid_width + 24
        overview_top = 62
        local_x = position.x() - overview_left
        local_y = position.y() - overview_top
        overview_width, overview_height = OVERVIEW_SIZE
        if not (
            0 <= local_x < overview_width
            and 0 <= local_y < overview_height
        ):
            return

        scale = min(
            overview_width / project.width,
            overview_height / project.height,
        )
        image_width = max(1, round(project.width * scale))
        image_height = max(1, round(project.height * scale))
        offset_x = (overview_width - image_width) // 2
        offset_y = (overview_height - image_height) // 2
        image_x = local_x - offset_x
        image_y = local_y - offset_y
        if not (0 <= image_x < image_width and 0 <= image_y < image_height):
            return
        column = min(
            project.width - 1,
            int(image_x * project.width / image_width),
        )
        row = min(
            project.height - 1,
            int(image_y * project.height / image_height),
        )
        self._select_page_for_cell(row, column)

    def _select_page_for_cell(self, row: int, column: int) -> bool:
        section = next(
            (
                candidate for candidate in self._page_sections
                if candidate.start_row <= row < candidate.end_row
                and candidate.start_column <= column < candidate.end_column
            ),
            None,
        )
        return bool(
            section is not None
            and self.sidebar.pages_panel.select_page(section.image_path)
        )

    @Slot(str)
    def _show_load_error(self, message: str) -> None:
        QMessageBox.warning(self, "Image load failed", message)

    @Slot(str)
    def _show_page_preview(self, image_path: str) -> None:
        self.canvas.clear_highlights()
        resolved_path = Path(image_path).resolve()
        self._active_page_section = next(
            (
                section for section in self._page_sections
                if section.image_path.resolve() == resolved_path
            ),
            None,
        )
        if self.canvas.show_preview(image_path):
            self.message_label.setText(f"Previewing {Path(image_path).name}")

    @Slot()
    def _restore_source_image(self) -> None:
        self.canvas.clear_mosaic_grid()
        self.canvas.clear_highlights()
        if self.canvas.restore_source_image():
            self.message_label.setText("Returned to source image editor")

    @Slot(int)
    def _on_sidebar_tab_changed(self, index: int) -> None:
        self._clear_cell_hover()
        widget = self.sidebar.widget(index)
        if widget in (
            self.sidebar.palette_panel,
            self.sidebar.summary_panel,
        ):
            current_source = self.canvas.source_image_path
            if (
                self._sherwin_preview_path is not None
                and self._sherwin_preview_path.exists()
                and current_source == self._sherwin_preview_source
                and self.canvas.show_preview(self._sherwin_preview_path)
            ):
                self.message_label.setText(
                    "Previewing unlabeled Sherwin-Williams colors"
                )
                if widget is self.sidebar.summary_panel:
                    self._highlight_summary_color(
                        self.sidebar.summary_panel.selected_palette_numbers()
                    )
                elif widget is self.sidebar.palette_panel:
                    self._highlight_summary_color(
                        self.sidebar.palette_panel.selected_palette_numbers()
                    )
        elif widget is self.sidebar.pages_panel:
            self.canvas.clear_highlights()
            selected_page = self.sidebar.pages_panel.current_page_path()
            if selected_page is not None:
                self._show_page_preview(selected_page)
                return
            current_source = self.canvas.source_image_path
            if (
                self._sherwin_preview_path is not None
                and self._sherwin_preview_path.exists()
                and current_source == self._sherwin_preview_source
                and self.canvas.show_preview(self._sherwin_preview_path)
            ):
                self.message_label.setText(
                    "Previewing Sherwin-Williams build mosaic"
                )
        elif widget is self.sidebar.settings_panel:
            self._restore_source_image()
            self._schedule_live_preview()

    @Slot(str)
    def _show_preview_mode(self, mode: str) -> None:
        if self.sidebar.currentWidget() is not self.sidebar.settings_panel:
            return
        if mode == "Original":
            self.sidebar.live_preview.setChecked(False)
            self._restore_source_image()
        elif mode == "Pixelated":
            self.sidebar.live_preview.setChecked(True)
            self._schedule_live_preview()
        elif mode == "Matched paint" and self._sherwin_preview_path:
            self.sidebar.live_preview.setChecked(False)
            self.canvas.show_preview(self._sherwin_preview_path)
        elif mode == "Numbered blueprint" and self._numbered_preview_path:
            self.sidebar.live_preview.setChecked(False)
            self.canvas.show_preview(self._numbered_preview_path)

    @Slot(object)
    def _choose_paint_override(self, palette_numbers: object) -> None:
        if self._active_project is None:
            return
        numbers = tuple(int(number) for number in palette_numbers)
        if not numbers:
            return
        query, accepted = QInputDialog.getText(
            self, f"Choose {self.sidebar.matcher.catalog_name} paint",
            "Enter a color name, SW code, or hex value:",
        )
        if not accepted:
            return
        matches = self.sidebar.matcher.find(query)
        if not matches:
            QMessageBox.information(self, "No match", "No catalog colors matched.")
            return
        labels = [f"{paint.display_code} · {paint.name} · {paint.hex_value}" for paint in matches]
        label, accepted = QInputDialog.getItem(
            self, "Lock paint match", "Paint:", labels, 0, False,
        )
        if not accepted:
            return
        paint = matches[labels.index(label)]
        for palette_number in numbers:
            self.sidebar.paint_overrides[palette_number] = paint.code
        self._rebuild_paint_plan()

    @Slot(object)
    def _merge_palette_colors(self, palette_numbers: object) -> None:
        numbers = tuple(int(number) for number in palette_numbers)
        if len(numbers) < 2 or self._active_paint_plan is None:
            return
        target = self._active_paint_plan.matches.get(numbers[0])
        if target is None:
            return
        for number in numbers:
            self.sidebar.paint_overrides[number] = target.color.code
        self._rebuild_paint_plan()

    @Slot(object)
    def _unlock_paint_overrides(self, palette_numbers: object) -> None:
        changed = False
        for number in palette_numbers:
            changed = self.sidebar.paint_overrides.pop(int(number), None) is not None or changed
        if changed:
            self._rebuild_paint_plan()

    def _rebuild_paint_plan(self, switch_tab: bool = True) -> None:
        if self._active_project is None:
            return
        positions: dict[int, list[tuple[int, int]]] = {}
        for project_row in self._active_project.grid:
            for cell in project_row:
                positions.setdefault(cell.color, []).append((cell.row, cell.column))
        self._active_paint_plan = self.sidebar.create_paint_plan(
            self._active_project.palette,
            self._active_project.color_counts,
            positions,
        )
        if switch_tab:
            self.sidebar.set_palette(
                self._active_project.palette,
                self._active_project.color_counts,
                self._active_paint_plan,
            )
        else:
            estimator = self.sidebar.paint_estimator()
            self.sidebar.palette_panel.set_palette(
                self._active_project.palette,
                self._active_project.color_counts,
                estimator,
                self._active_paint_plan,
            )
            self.sidebar.summary_panel.set_plan(self._active_paint_plan)
        self.message_label.setText("Paint choices updated and locked")

    @Slot(str)
    def _on_paint_company_changed(self, catalog_name: str) -> None:
        # Selecting a catalog is only a settings change.  Rebuilding here used
        # to replace the current paint plan and send the user to Summary even
        # though the rest of the blueprint had not been regenerated yet.
        self.sidebar.setCurrentWidget(self.sidebar.settings_panel)
        self.sidebar.set_result_tabs_enabled(False)
        self._blueprint_stale = True
        self.sidebar.settings_panel.generation_status.setText(
            f"Blueprint out of date — generate to apply {catalog_name}"
        )
        if self._active_project is None:
            self.message_label.setText(f"Paint company: {catalog_name}")
        else:
            self.message_label.setText(
                f"Paint company: {catalog_name} — regenerate the blueprint to apply"
            )

    def _apply_tile_color(
        self, row: int, column: int, color: int, refresh: bool,
    ) -> None:
        if self._active_project is None or color not in self._active_project.palette:
            return
        cell = self._active_project.grid[row][column]
        old_color = cell.color
        if old_color == color:
            return
        cell.color = color
        cell.rgb = self._active_project.palette[color]
        self._active_project.color_counts[old_color] -= 1
        self._active_project.color_counts[color] = (
            self._active_project.color_counts.get(color, 0) + 1
        )
        if not refresh:
            return
        self._rebuild_paint_plan(switch_tab=False)
        if self._active_paint_plan is not None:
            render_master(
                self._active_project,
                color_overrides=self._active_paint_plan.color_overrides,
                filename_tag="SherwinWilliams_NoCellLabels",
                palette_color_count=len(self._active_paint_plan.rows),
                title_suffix="Sherwin-Williams — No Cell Labels",
                show_labels=False,
                show_grid=False,
            )
            if self._sherwin_preview_path is not None:
                self.canvas.show_preview(self._sherwin_preview_path)

    def _render_edited_preview(self) -> None:
        if self._active_project is None or self._active_paint_plan is None:
            return
        render_master(
            self._active_project,
            color_overrides=self._active_paint_plan.color_overrides,
            filename_tag="SherwinWilliams_NoCellLabels",
            palette_color_count=len(self._active_paint_plan.rows),
            title_suffix="Sherwin-Williams - No Cell Labels",
            show_labels=False,
            show_grid=False,
        )
        if self._sherwin_preview_path is not None:
            self.canvas.show_preview(self._sherwin_preview_path)

    @Slot(object)
    def _highlight_summary_color(self, palette_numbers: object) -> None:
        source_path = self.canvas.source_image_path
        if (
            self._active_project is None
            or self._active_project.source_path is None
            or source_path is None
            or self._active_project.source_path.resolve()
            != Path(source_path).resolve()
        ):
            self.canvas.clear_highlights()
            return
        selected = {int(number) for number in palette_numbers}
        rectangles = [
            QRectF(
                BORDER + cell.column * CELL_SIZE,
                BORDER + cell.row * CELL_SIZE,
                CELL_SIZE,
                CELL_SIZE,
            )
            for row in self._active_project.grid
            for cell in row
            if cell.color in selected
        ]
        self.canvas.set_highlight_rects(rectangles)
        if selected:
            self.message_label.setText(
                f"Highlighted {len(rectangles):,} squares for selected paint color"
            )

    @Slot()
    def about(self) -> None:
        QMessageBox.about(
            self, "About Blueprint Mosaic Studio",
            "Blueprint Mosaic Studio\nInteractive mosaic editor — Milestone 1",
        )
