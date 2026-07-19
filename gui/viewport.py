"""State shared by the editor canvas and application chrome."""

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF


@dataclass(slots=True)
class ViewportModel:
    """Serializable viewport state expressed in image-pixel coordinates."""

    image_path: str | None = None
    image_rect: QRectF = field(default_factory=QRectF)
    crop_rect: QRectF = field(default_factory=QRectF)
    mouse_position: QPointF = field(default_factory=QPointF)
    zoom: float = 1.0

    @property
    def has_image(self) -> bool:
        return self.image_path is not None and not self.image_rect.isEmpty()

    def reset(self, image_path: str, image_rect: QRectF) -> None:
        self.image_path = image_path
        self.image_rect = QRectF(image_rect)
        self.crop_rect = QRectF(image_rect)
        self.mouse_position = QPointF()
        self.zoom = 1.0

