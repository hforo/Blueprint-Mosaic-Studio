"""Interactive crop item used by the graphics-scene editor."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
)


class HandlePosition(Enum):
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    RIGHT = "right"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM = "bottom"
    BOTTOM_LEFT = "bottom_left"
    LEFT = "left"


class CropSignals(QObject):
    """Qt signal bridge for the non-QObject graphics item."""

    geometry_changed = Signal(QRectF)


class HandleItem(QGraphicsRectItem):
    """A resize handle that delegates pointer movement to its crop item."""

    SIZE = 10.0

    def __init__(self, position: HandlePosition, parent: CropItem) -> None:
        half = self.SIZE / 2.0
        super().__init__(-half, -half, self.SIZE, self.SIZE, parent)
        self.position = position
        self._crop_item = parent
        self._press_scene_position = QPointF()
        self._starting_rect = QRectF()
        self.setBrush(QBrush(QColor("white")))
        self.setPen(QPen(QColor(30, 110, 220), 1.5))
        self.setZValue(2)
        self.setCursor(self._cursor_for_position(position))
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    @staticmethod
    def _cursor_for_position(position: HandlePosition) -> Qt.CursorShape:
        if position in (HandlePosition.TOP_LEFT, HandlePosition.BOTTOM_RIGHT):
            return Qt.CursorShape.SizeFDiagCursor
        if position in (HandlePosition.TOP_RIGHT, HandlePosition.BOTTOM_LEFT):
            return Qt.CursorShape.SizeBDiagCursor
        if position in (HandlePosition.TOP, HandlePosition.BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.SizeHorCursor

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._press_scene_position = event.scenePos()
        self._starting_rect = self._crop_item.scene_crop_rect()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        delta = event.scenePos() - self._press_scene_position
        self._crop_item.resize_from_handle(
            self.position,
            self._starting_rect,
            delta,
        )
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        event.accept()


class CropItem(QGraphicsRectItem):
    """Movable, resizable crop rectangle constrained to an image rectangle."""

    MINIMUM_SIZE = 8.0

    def __init__(self, crop_rect: QRectF, bounds: QRectF) -> None:
        super().__init__(0.0, 0.0, crop_rect.width(), crop_rect.height())
        self.signals = CropSignals()
        self._bounds = QRectF(bounds)
        self._updating_geometry = False
        self._handles = {
            position: HandleItem(position, self) for position in HandlePosition
        }

        self.setPos(crop_rect.topLeft())
        self.setPen(QPen(QColor(60, 150, 255), 2.0))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setZValue(10)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._position_handles()

    def scene_crop_rect(self) -> QRectF:
        return QRectF(self.pos(), self.rect().size())

    def set_crop_rect(self, crop_rect: QRectF, emit: bool = True) -> None:
        constrained = crop_rect.normalized().intersected(self._bounds)
        if constrained.width() < self.MINIMUM_SIZE:
            constrained.setWidth(min(self.MINIMUM_SIZE, self._bounds.width()))
        if constrained.height() < self.MINIMUM_SIZE:
            constrained.setHeight(min(self.MINIMUM_SIZE, self._bounds.height()))
        constrained.moveLeft(
            min(max(constrained.left(), self._bounds.left()),
                self._bounds.right() - constrained.width())
        )
        constrained.moveTop(
            min(max(constrained.top(), self._bounds.top()),
                self._bounds.bottom() - constrained.height())
        )

        self._updating_geometry = True
        self.prepareGeometryChange()
        self.setRect(0.0, 0.0, constrained.width(), constrained.height())
        self.setPos(constrained.topLeft())
        self._updating_geometry = False
        self._position_handles()
        if emit:
            self.signals.geometry_changed.emit(self.scene_crop_rect())

    def resize_from_handle(
        self,
        position: HandlePosition,
        starting_rect: QRectF,
        delta: QPointF,
    ) -> None:
        left = starting_rect.left()
        top = starting_rect.top()
        right = starting_rect.right()
        bottom = starting_rect.bottom()

        if position in (
            HandlePosition.TOP_LEFT,
            HandlePosition.LEFT,
            HandlePosition.BOTTOM_LEFT,
        ):
            left = min(starting_rect.left() + delta.x(),
                       right - self.MINIMUM_SIZE)
        if position in (
            HandlePosition.TOP_RIGHT,
            HandlePosition.RIGHT,
            HandlePosition.BOTTOM_RIGHT,
        ):
            right = max(starting_rect.right() + delta.x(),
                        left + self.MINIMUM_SIZE)
        if position in (
            HandlePosition.TOP_LEFT,
            HandlePosition.TOP,
            HandlePosition.TOP_RIGHT,
        ):
            top = min(starting_rect.top() + delta.y(),
                      bottom - self.MINIMUM_SIZE)
        if position in (
            HandlePosition.BOTTOM_LEFT,
            HandlePosition.BOTTOM,
            HandlePosition.BOTTOM_RIGHT,
        ):
            bottom = max(starting_rect.bottom() + delta.y(),
                         top + self.MINIMUM_SIZE)

        left = max(left, self._bounds.left())
        top = max(top, self._bounds.top())
        right = min(right, self._bounds.right())
        bottom = min(bottom, self._bounds.bottom())
        self.set_crop_rect(QRectF(QPointF(left, top), QPointF(right, bottom)))

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: object,
    ) -> object:
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and not self._updating_geometry
            and isinstance(value, QPointF)
        ):
            maximum_x = self._bounds.right() - self.rect().width()
            maximum_y = self._bounds.bottom() - self.rect().height()
            return QPointF(
                min(max(value.x(), self._bounds.left()), maximum_x),
                min(max(value.y(), self._bounds.top()), maximum_y),
            )
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._updating_geometry
        ):
            self.signals.geometry_changed.emit(self.scene_crop_rect())
        return super().itemChange(change, value)

    def _position_handles(self) -> None:
        rect = self.rect()
        positions = {
            HandlePosition.TOP_LEFT: rect.topLeft(),
            HandlePosition.TOP: QPointF(rect.center().x(), rect.top()),
            HandlePosition.TOP_RIGHT: rect.topRight(),
            HandlePosition.RIGHT: QPointF(rect.right(), rect.center().y()),
            HandlePosition.BOTTOM_RIGHT: rect.bottomRight(),
            HandlePosition.BOTTOM: QPointF(rect.center().x(), rect.bottom()),
            HandlePosition.BOTTOM_LEFT: rect.bottomLeft(),
            HandlePosition.LEFT: QPointF(rect.left(), rect.center().y()),
        }
        for position, point in positions.items():
            self._handles[position].setPos(point)

