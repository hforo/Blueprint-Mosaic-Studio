"""Editor controls displayed beside the graphics canvas."""

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


class Sidebar(QWidget):
    """Configuration panel for mosaic generation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(280)
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
        layout.addWidget(settings)

        self.generate = QPushButton("Generate Blueprint")
        self.generate.setMinimumHeight(38)
        layout.addWidget(self.generate)
        layout.addStretch()

