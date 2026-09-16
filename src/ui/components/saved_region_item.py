from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
)

from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.geometry_helpers import (
    clamp_move,
    clamp_resize,
    move_rect,
    resize_rect,
)


class SavedRegionSignals(QObject):
    region_selected = Signal(str)
    region_geometry_changed = Signal(str, QRectF)


class SavedRegionItem(QGraphicsRectItem):
    """
    Representa una región guardada en el UI.
    Agnóstica a coordenadas nativas PDF; trabaja puramente en Scene/Render space.
    """

    BASE_HANDLE_SIZE = 8.0
    BASE_MIN_SIZE = 10.0

    def __init__(
        self, region_id: str, rendered_rect: QRectF, page_width: float, page_height: float
    ):
        super().__init__(rendered_rect)
        self.region_id = region_id
        self._page_bounds = Rect(0, 0, page_width, page_height)
        self._zoom_factor = 1.0

        self.signals = SavedRegionSignals()

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        # Style
        self._default_pen = QPen(QColor(255, 165, 0))  # Orange
        self._default_brush = QBrush(QColor(255, 165, 0, 40))
        self._selected_pen = QPen(QColor(255, 140, 0))  # Dark orange
        self._selected_pen.setWidth(2)
        self._selected_brush = QBrush(QColor(255, 165, 0, 60))

        self.setPen(self._default_pen)
        self.setBrush(self._default_brush)

        # Interaction state
        self._interaction_mode = "NONE"  # NONE, MOVE, TL, TR, BL, BR
        self._original_rect = self.rect()
        self._start_pos = QPointF()
        self._start_rect = self.rect()
        self._editing_enabled = True

    def set_editing_enabled(self, enabled: bool):
        self._editing_enabled = enabled
        self.setFlag(QGraphicsItem.ItemIsSelectable, enabled)
        if not enabled:
            self.setSelected(False)
            self.setCursor(Qt.ArrowCursor)

    @property
    def handle_size(self) -> float:
        return self.BASE_HANDLE_SIZE / max(0.1, self._zoom_factor)

    @property
    def min_size(self) -> float:
        return self.BASE_MIN_SIZE / max(0.1, self._zoom_factor)

    def update_pen_width(self, zoom_factor: float):
        """Ajusta el grosor según el nivel de zoom de la vista."""
        self._zoom_factor = zoom_factor
        w = max(1.0, 2.0 / zoom_factor)
        self._default_pen.setWidthF(w)
        self._selected_pen.setWidthF(w * 1.5)
        if self.isSelected():
            self.setPen(self._selected_pen)
        else:
            self.setPen(self._default_pen)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            # Draw handles
            r = self.rect()
            hs = self.handle_size
            half = hs / 2.0

            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(0, 0, 0)))

            painter.drawRect(QRectF(r.left() - half, r.top() - half, hs, hs))  # TL
            painter.drawRect(QRectF(r.right() - half, r.top() - half, hs, hs))  # TR
            painter.drawRect(QRectF(r.left() - half, r.bottom() - half, hs, hs))  # BL
            painter.drawRect(QRectF(r.right() - half, r.bottom() - half, hs, hs))  # BR

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedChange:
            if value:
                self.setPen(self._selected_pen)
                self.setBrush(self._selected_brush)
                self.signals.region_selected.emit(self.region_id)
            else:
                self.setPen(self._default_pen)
                self.setBrush(self._default_brush)
        return super().itemChange(change, value)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
        if not self._editing_enabled or not self.isSelected():
            self.setCursor(Qt.ArrowCursor)
            super().hoverMoveEvent(event)
            return

        mode = self._get_interaction_mode(event.pos())
        if mode in ("TL", "BR"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif mode in ("TR", "BL"):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if not self._editing_enabled:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.LeftButton:
            if not self.isSelected():
                self.setSelected(True)
            self._interaction_mode = self._get_interaction_mode(event.pos())
            self._start_pos = event.scenePos()
            self._start_rect = self.rect()
            self._original_rect = self.rect()  # For Esc cancellation
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._interaction_mode == "NONE":
            super().mouseMoveEvent(event)
            return

        delta = event.scenePos() - self._start_pos
        dx = delta.x()
        dy = delta.y()

        # Convert QRectF to Rect neutral
        sr = self._start_rect
        rect = Rect(sr.left(), sr.top(), sr.right(), sr.bottom())

        if self._interaction_mode == "MOVE":
            new_rect = move_rect(rect, dx, dy)
            new_rect = clamp_move(new_rect, self._page_bounds)
        else:
            new_rect = resize_rect(rect, self._interaction_mode, dx, dy, min_size=self.min_size)
            new_rect = clamp_resize(new_rect, self._page_bounds)

        self.setRect(QRectF(new_rect.x0, new_rect.y0, new_rect.width, new_rect.height))
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._interaction_mode != "NONE":
            final_rect = self.rect()
            if final_rect != self._original_rect:
                # Emit change
                self.signals.region_geometry_changed.emit(self.region_id, final_rect)
            self._interaction_mode = "NONE"
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._interaction_mode != "NONE":
            self.setRect(self._original_rect)
            self._interaction_mode = "NONE"
            event.accept()
        else:
            super().keyPressEvent(event)

    def _get_interaction_mode(self, pos: QPointF) -> str:
        r = self.rect()
        hs = self.handle_size

        tl = QRectF(r.left() - hs / 2, r.top() - hs / 2, hs, hs)
        tr = QRectF(r.right() - hs / 2, r.top() - hs / 2, hs, hs)
        bl = QRectF(r.left() - hs / 2, r.bottom() - hs / 2, hs, hs)
        br = QRectF(r.right() - hs / 2, r.bottom() - hs / 2, hs, hs)

        if tl.contains(pos):
            return "TL"
        if tr.contains(pos):
            return "TR"
        if bl.contains(pos):
            return "BL"
        if br.contains(pos):
            return "BR"
        return "MOVE"
