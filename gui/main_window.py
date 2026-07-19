"""Application window coordinating editor widgets and the render pipeline."""

from __future__ import annotations

from math import ceil
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QWidget

from image import process_image
from pages import render_pages
from render import render_master

from .canvas import CanvasView
from .sidebar import Sidebar


class MainWindow(QMainWindow):
    """Top-level application shell; domain behavior lives in dedicated modules."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Blueprint Mosaic Studio")
        self.resize(1600, 900)
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
        self.message_label = QLabel("Ready — open or drop an image")
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
        generate_action = QAction("Generate &Blueprint", self)
        generate_action.setShortcut("Ctrl+G")
        generate_action.triggered.connect(self.generate_blueprint)
        file_menu.addAction(generate_action)
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

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        self.sidebar.generate.clicked.connect(self.generate_blueprint)
        self.canvas.zoom_changed.connect(self._update_zoom_status)
        self.canvas.image_changed.connect(self._update_image_status)
        self.canvas.crop_changed.connect(self._update_crop_status)
        self.canvas.mouse_position_changed.connect(self._update_mouse_status)
        self.canvas.image_load_failed.connect(self._show_load_error)

    @Slot()
    def open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)",
        )
        if filename:
            self.canvas.load_image(filename)

    @Slot()
    def generate_blueprint(self) -> None:
        """Run the established image, master, and printable-page pipeline."""
        image_path = self.canvas.model.image_path
        if image_path is None:
            QMessageBox.information(self, "No image", "Open an image first.")
            return
        crop = self.canvas.crop_rect()
        grid_width = self.sidebar.grid.value()
        grid_height = max(1, round(grid_width * crop.height() / crop.width()))
        crop_box = (int(crop.left()), int(crop.top()),
                    int(ceil(crop.right())), int(ceil(crop.bottom())))

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.message_label.setText("Generating blueprint…")
        QApplication.processEvents()
        try:
            project = process_image(
                Path(image_path), grid_width, grid_height,
                self.sidebar.colors.value(),
                dither=self.sidebar.dither.isChecked(), crop_box=crop_box,
            )
            render_master(project)
            render_pages(project)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Generation failed", str(error))
            self.message_label.setText("Blueprint generation failed")
        else:
            self.message_label.setText("Blueprint and printable pages generated")
        finally:
            QApplication.restoreOverrideCursor()

    @Slot(float)
    def _update_zoom_status(self, percentage: float) -> None:
        self.zoom_label.setText(f"Zoom: {percentage:.0f}%")

    @Slot(str, int, int)
    def _update_image_status(self, path: str, width: int, height: int) -> None:
        self.image_label.setText(f"Image: {width} × {height} px")
        self.message_label.setText(f"Loaded {Path(path).name}")

    @Slot(QRectF)
    def _update_crop_status(self, rect: QRectF) -> None:
        self.crop_label.setText(
            f"Crop: {round(rect.width())} × {round(rect.height())} px"
        )

    @Slot(QPointF)
    def _update_mouse_status(self, position: QPointF) -> None:
        if self.canvas.model.image_rect.contains(position):
            self.mouse_label.setText(
                f"Cursor: {int(position.x())}, {int(position.y())}"
            )
        else:
            self.mouse_label.setText("Cursor: —")

    @Slot(str)
    def _show_load_error(self, message: str) -> None:
        QMessageBox.warning(self, "Image load failed", message)

    @Slot()
    def about(self) -> None:
        QMessageBox.about(
            self, "About Blueprint Mosaic Studio",
            "Blueprint Mosaic Studio\nInteractive mosaic editor — Milestone 1",
        )

