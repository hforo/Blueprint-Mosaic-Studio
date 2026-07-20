"""Professional graphics-view image editing canvas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent,
    QBrush, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap,
    QTransform, QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from .crop_item import CropItem
from .viewport import ViewportModel


IMAGE_EXTENSIONS = {
    ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"
}


class CanvasScene(QGraphicsScene):
    """Scene that shades the image area outside the active crop."""

    def __init__(self, parent: QGraphicsView | None = None) -> None:
        super().__init__(parent)
        self.image_rect = QRectF()
        self.crop_rect = QRectF()

    def set_overlay_geometry(self, image_rect: QRectF, crop_rect: QRectF) -> None:
        self.image_rect = QRectF(image_rect)
        self.crop_rect = QRectF(crop_rect)
        self.invalidate(self.image_rect, QGraphicsScene.SceneLayer.ForegroundLayer)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self.image_rect.isEmpty() or self.crop_rect.isEmpty():
            return
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 125))
        image = self.image_rect
        crop = self.crop_rect.intersected(image)
        painter.drawRect(QRectF(image.left(), image.top(), image.width(),
                                crop.top() - image.top()))
        painter.drawRect(QRectF(image.left(), crop.bottom(), image.width(),
                                image.bottom() - crop.bottom()))
        painter.drawRect(QRectF(image.left(), crop.top(), crop.left() - image.left(),
                                crop.height()))
        painter.drawRect(QRectF(crop.right(), crop.top(), image.right() - crop.right(),
                                crop.height()))
        painter.restore()


class CanvasView(QGraphicsView):
    """Image editor responsible for navigation, image drops, and crop display."""

    zoom_changed = Signal(float)
    image_changed = Signal(str, int, int)
    crop_changed = Signal(QRectF)
    mouse_position_changed = Signal(QPointF)
    image_clicked = Signal(QPointF)
    image_load_failed = Signal(str)

    MIN_ZOOM = 0.02
    MAX_ZOOM = 64.0
    ZOOM_STEP = 1.15
    MAX_PREVIEW_DIMENSION = 4096
    IMAGE_DECODE_LIMIT_MB = 1024

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = ViewportModel()
        self.canvas_scene = CanvasScene(self)
        self.setScene(self.canvas_scene)
        self.image_item: QGraphicsPixmapItem | None = None
        self.crop_item: CropItem | None = None
        self.highlight_item: QGraphicsPathItem | None = None
        self.grid_items: list[QGraphicsPathItem] = []
        self._panning = False
        self._pan_start = QPoint()
        self._preview_source_state: tuple[str, QRectF] | None = None

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QColor(42, 45, 49))
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def load_image(self, filename: str | Path) -> bool:
        self._preview_source_state = None
        self.highlight_item = None
        self.grid_items = []
        path = Path(filename).expanduser().resolve()
        # Qt rejects images whose uncompressed source exceeds its conservative
        # default, even when the reader is asked for a scaled preview.
        QImageReader.setAllocationLimit(self.IMAGE_DECODE_LIMIT_MB)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        source_size = reader.size()
        if not source_size.isValid():
            self.image_load_failed.emit(f"Unable to load image: {path}")
            return False

        preview_size = self._preview_size(source_size)
        if preview_size != source_size:
            reader.setScaledSize(preview_size)
        preview_image = reader.read()
        if preview_image.isNull():
            detail = reader.errorString() or "unsupported or corrupt image"
            self.image_load_failed.emit(f"Unable to load image: {path}\n{detail}")
            return False
        pixmap = QPixmap.fromImage(preview_image)

        self.canvas_scene.clear()
        self.image_item = self.canvas_scene.addPixmap(pixmap)
        self.image_item.setZValue(0)
        self.image_item.setTransform(QTransform.fromScale(
            source_size.width() / pixmap.width(),
            source_size.height() / pixmap.height(),
        ))
        image_rect = QRectF(
            0.0, 0.0, source_size.width(), source_size.height()
        )
        self.canvas_scene.setSceneRect(image_rect)
        self.model.reset(str(path), image_rect)

        self.crop_item = CropItem(image_rect, image_rect)
        self.crop_item.signals.geometry_changed.connect(self._on_crop_changed)
        self.canvas_scene.addItem(self.crop_item)
        self.canvas_scene.set_overlay_geometry(image_rect, image_rect)
        self.fit_to_window()
        self.image_changed.emit(
            str(path), source_size.width(), source_size.height()
        )
        self.crop_changed.emit(QRectF(image_rect))
        return True

    def set_highlight_rects(self, rectangles: list[QRectF]) -> None:
        """Highlight a collection of image-space rectangles as one scene item."""
        self.clear_highlights()
        if not rectangles:
            return
        path = QPainterPath()
        for rectangle in rectangles:
            path.addRect(rectangle)
        item = QGraphicsPathItem(path)
        pen = QPen(QColor(255, 75, 20), 2.0)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setBrush(QBrush(QColor(255, 215, 0, 105)))
        item.setZValue(100)
        self.canvas_scene.addItem(item)
        self.highlight_item = item

    def clear_highlights(self) -> None:
        if self.highlight_item is not None:
            if self.highlight_item.scene() is self.canvas_scene:
                self.canvas_scene.removeItem(self.highlight_item)
            self.highlight_item = None

    def set_mosaic_grid(
        self,
        columns: int,
        rows: int,
        origin: QPointF,
        cell_size: float,
        heavy_every: int = 4,
    ) -> None:
        """Draw a cosmetic vector grid that stays visible at every zoom."""
        self.clear_mosaic_grid()
        if columns <= 0 or rows <= 0 or cell_size <= 0:
            return
        light_path = QPainterPath()
        heavy_path = QPainterPath()
        width = columns * cell_size
        height = rows * cell_size
        for column in range(columns + 1):
            x = origin.x() + column * cell_size
            path = heavy_path if column % heavy_every == 0 else light_path
            path.moveTo(x, origin.y())
            path.lineTo(x, origin.y() + height)
        for row in range(rows + 1):
            y = origin.y() + row * cell_size
            path = heavy_path if row % heavy_every == 0 else light_path
            path.moveTo(origin.x(), y)
            path.lineTo(origin.x() + width, y)

        for path, color, line_width in (
            (light_path, QColor(80, 80, 80, 210), 1.0),
            (heavy_path, QColor(10, 10, 10, 235), 2.0),
        ):
            item = QGraphicsPathItem(path)
            pen = QPen(color, line_width)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setBrush(Qt.BrushStyle.NoBrush)
            item.setZValue(50)
            self.canvas_scene.addItem(item)
            self.grid_items.append(item)

    def clear_mosaic_grid(self) -> None:
        for item in self.grid_items:
            if item.scene() is self.canvas_scene:
                self.canvas_scene.removeItem(item)
        self.grid_items.clear()

    @property
    def source_image_path(self) -> str | None:
        if self._preview_source_state is not None:
            return self._preview_source_state[0]
        return self.model.image_path

    def source_crop_rect(self) -> QRectF:
        if self._preview_source_state is not None:
            return QRectF(self._preview_source_state[1])
        return self.crop_rect()

    def show_preview(self, filename: str | Path) -> bool:
        """Show a generated artifact without replacing the editable source."""
        source_state = self._preview_source_state
        if source_state is None:
            if not self.model.has_image or self.model.image_path is None:
                return False
            source_state = (self.model.image_path, self.crop_rect())
        if not self.load_image(filename):
            self._preview_source_state = source_state
            return False
        self._preview_source_state = source_state
        if self.crop_item is not None:
            self.canvas_scene.removeItem(self.crop_item)
            self.crop_item = None
        self.model.crop_rect = QRectF()
        self.canvas_scene.set_overlay_geometry(self.model.image_rect, QRectF())
        self.crop_changed.emit(QRectF())
        return True

    def show_live_preview(self, image: QImage) -> bool:
        """Display an in-memory preview while retaining source and crop state."""
        if image.isNull():
            return False
        source_state = self._preview_source_state
        if source_state is None:
            if not self.model.has_image or self.model.image_path is None:
                return False
            source_state = (self.model.image_path, self.crop_rect())

        self.canvas_scene.clear()
        self.highlight_item = None
        self.grid_items = []
        self.crop_item = None
        pixmap = QPixmap.fromImage(image)
        self.image_item = self.canvas_scene.addPixmap(pixmap)
        self.image_item.setZValue(0)
        image_rect = QRectF(0.0, 0.0, image.width(), image.height())
        self.canvas_scene.setSceneRect(image_rect)
        self.model.reset(source_state[0], image_rect)
        self.model.crop_rect = QRectF()
        self._preview_source_state = source_state
        self.canvas_scene.set_overlay_geometry(image_rect, QRectF())
        self.fit_to_window()
        self.crop_changed.emit(QRectF())
        return True

    def restore_source_image(self) -> bool:
        """Return from artifact preview to the original image and crop."""
        if self._preview_source_state is None:
            return False
        source_path, crop_rect = self._preview_source_state
        self._preview_source_state = None
        if not self.load_image(source_path):
            self._preview_source_state = (source_path, crop_rect)
            return False
        if self.crop_item is not None:
            self.crop_item.set_crop_rect(crop_rect)
        return True

    def fit_to_window(self) -> None:
        if not self.model.has_image:
            return
        self.fitInView(self.model.image_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._update_zoom()

    def reset_zoom(self) -> None:
        if not self.model.has_image:
            return
        scene_center = self.mapToScene(self.viewport().rect().center())
        self.resetTransform()
        self.centerOn(scene_center)
        self._update_zoom()

    def crop_rect(self) -> QRectF:
        return QRectF(self.model.crop_rect)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.model.has_image or event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        current_zoom = self.transform().m11()
        factor = self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
        target_zoom = min(max(current_zoom * factor, self.MIN_ZOOM), self.MAX_ZOOM)
        factor = target_zoom / current_zoom
        scene_before = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        scene_after = self.mapToScene(event.position().toPoint())
        delta = scene_after - scene_before
        self.translate(delta.x(), delta.y())
        self._update_zoom()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            scene_position = self.mapToScene(event.position().toPoint())
            if self.model.image_rect.contains(scene_position):
                self.image_clicked.emit(scene_position)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_position = self.mapToScene(event.position().toPoint())
        self.model.mouse_position = scene_position
        self.mouse_position_changed.emit(scene_position)
        if self._panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._first_supported_path(event.mimeData().urls()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._first_supported_path(event.mimeData().urls()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._first_supported_path(event.mimeData().urls())
        if path is not None and self.load_image(path):
            event.acceptProposedAction()
        else:
            event.ignore()

    @staticmethod
    def _first_supported_path(urls) -> Path | None:
        for url in urls:
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in IMAGE_EXTENSIONS:
                    return path
        return None

    @classmethod
    def _preview_size(cls, source_size: QSize) -> QSize:
        if max(source_size.width(), source_size.height()) <= cls.MAX_PREVIEW_DIMENSION:
            return QSize(source_size)
        return source_size.scaled(
            cls.MAX_PREVIEW_DIMENSION,
            cls.MAX_PREVIEW_DIMENSION,
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _on_crop_changed(self, crop_rect: QRectF) -> None:
        self.model.crop_rect = QRectF(crop_rect)
        self.canvas_scene.set_overlay_geometry(self.model.image_rect, crop_rect)
        self.crop_changed.emit(QRectF(crop_rect))

    def _update_zoom(self) -> None:
        self.model.zoom = self.transform().m11()
        self.zoom_changed.emit(self.model.zoom * 100.0)


Canvas = CanvasView
