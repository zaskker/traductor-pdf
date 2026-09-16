from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPen, QTextOption
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from src.domain.models.enums import FitStatus
from src.domain.value_objects.layout import RenderedTextPreview
from src.domain.value_objects.render_plan import RegionRenderPlan


def qimage_from_rendered_text_preview(preview: RenderedTextPreview) -> QImage:
    """Construye de forma segura y autoritativa una QImage a partir de un RenderedTextPreview."""
    if not preview:
        return QImage()

    fmt = QImage.Format_RGBA8888 if preview.channels == 4 else QImage.Format_RGB888

    raw_image = QImage(
        preview.samples,
        preview.width,
        preview.height,
        preview.stride,
        fmt,
    )
    return raw_image.copy()


class TranslationPreviewItem(QGraphicsRectItem):
    """
    Overlay estático no interactivo que muestra el texto traducido sobre la región en el PDF.
    Vive en Scene coordinates y se transforma automáticamente con la QGraphicsView.
    """

    def __init__(
        self,
        region_id: str,
        rendered_rect: QRectF,
        layout: RegionRenderPlan | None,
        fallback_text: str,
        rendered_preview: RenderedTextPreview | None = None,
        background_rgb: tuple[int, int, int] | None = None,
    ):
        super().__init__(rendered_rect)
        self.region_id = region_id
        self._layout = layout
        self._fallback_text = fallback_text
        self._rendered_preview = rendered_preview

        # Hacerlo completamente no interactivo
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsFocusable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)

        # Style (Fondo opaco del color analizado o blanco fallback)
        if background_rgb:
            self.setBrush(QBrush(QColor(background_rgb[0], background_rgb[1], background_rgb[2], 255)))
        else:
            self.setBrush(QBrush(QColor(255, 255, 255, 255)))
        self.setPen(QPen(Qt.NoPen))

        # No guardamos un QFont global. Cada bloque tiene su font size.
        self._fallback_default_font = QFont("Arial", 12)

        self._preview_image = QImage()
        if self._rendered_preview:
            self._preview_image = qimage_from_rendered_text_preview(self._rendered_preview)

        self._text_option = QTextOption()
        self._text_option.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        # Only wrap if we don't have definitive blocks
        if not self._layout or self._layout.fit_status == FitStatus.OVERFLOW or not self._layout.blocks:
            self._text_option.setWrapMode(QTextOption.WordWrap)
        else:
            self._text_option.setWrapMode(QTextOption.NoWrap)

    def paint(self, painter, option, widget):
        # 1. Dibujar el fondo
        super().paint(painter, option, widget)

        painter.save()
        painter.setClipRect(self.rect())

        is_overflow = self._layout and self._layout.fit_status == FitStatus.OVERFLOW
        if is_overflow:
            # Dibujar borde rojo de advertencia
            pen = QPen(QColor(255, 0, 0))
            pen.setStyle(Qt.DashLine)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self.rect())

            # Texto atenuado/rojo para diagnóstico
            painter.setPen(QPen(QColor(200, 0, 0)))
        else:
            painter.setPen(QPen(QColor(0, 0, 0)))

        if not is_overflow and not self._preview_image.isNull():
            # Habilitar suavizado al redimensionar si hay decimales en render_scale vs scene
            from PySide6.QtGui import QPainter

            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

            # Draw the image scaled into our rect
            painter.drawImage(self.rect(), self._preview_image)

        else:
            # Fallback diagnostic rendering
            if self._layout and self._layout.blocks:
                from PySide6.QtGui import QFontMetricsF
                from src.domain.models.enums import TextAlignment
                for block in self._layout.blocks:
                    block_font = QFont(block.font_family or "Arial")
                    block_font.setPointSizeF(block.font_size)
                    painter.setFont(block_font)
                    
                    option = QTextOption()
                    if block.alignment == TextAlignment.LEFT:
                        option.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                    elif block.alignment == TextAlignment.CENTER:
                        option.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
                    elif block.alignment == TextAlignment.RIGHT:
                        option.setAlignment(Qt.AlignRight | Qt.AlignTop)
                    elif block.alignment == TextAlignment.JUSTIFY:
                        option.setAlignment(Qt.AlignJustify | Qt.AlignTop)
                    
                    # block.rect is in domain coordinates.
                    # We are in scene/local coordinates. If we don't have a mapper here, 
                    # we can only do a rough approximation or assume scene coords = domain coords 
                    # but wait, the preview's rect was provided via effective_qrect!
                    # For a simple fallback, we just draw the text inside the block rect translated?
                    # The user said: "renderizar cada bloque usando SU propia metadata."
                    # If local coordinate system is 0,0 based or scene based?
                    # Since it inherits QGraphicsRectItem, self.rect() is the bounding rect.
                    # The RegionRenderPlan target_rect is in domain coords, and blocks are in domain coords.
                    # To draw properly without matrix, we map block.rect relative to self._layout.target_rect.
                    
                    plan_w = self._layout.target_rect.width
                    plan_h = self._layout.target_rect.height
                    item_rect = self.rect()
                    
                    if plan_w > 0 and plan_h > 0:
                        scale_x = item_rect.width() / plan_w
                        scale_y = item_rect.height() / plan_h
                        
                        b_x = item_rect.x() + (block.rect.x0 - self._layout.target_rect.x0) * scale_x
                        b_y = item_rect.y() + (block.rect.y0 - self._layout.target_rect.y0) * scale_y
                        b_w = block.rect.width * scale_x
                        b_h = block.rect.height * scale_y
                        
                        painter.drawText(QRectF(b_x, b_y, b_w, b_h), block.text, option)
            else:
                painter.setFont(self._fallback_default_font)
                text_rect = self.rect().adjusted(2.0, 2.0, -2.0, -2.0)
                painter.drawText(text_rect, self._fallback_text, self._text_option)

        painter.restore()
