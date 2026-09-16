from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from src.application.dtos.pdf_selection import PdfSelection
from src.application.dtos.rendered_page import RenderedPage
from src.domain.models.enums import RegionStatus
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.ui.components.saved_region_item import SavedRegionItem
from src.ui.components.translation_preview_item import TranslationPreviewItem
from src.ui.viewmodels.pdf_viewer_viewmodel import ZoomMode


class PdfViewWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setBackgroundBrush(QColor(60, 60, 60))  # Neutro oscuro

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self._current_page: RenderedPage | None = None
        self._zoom_mode: ZoomMode = ZoomMode.FIT_WIDTH
        self._zoom_factor: float = 1.0

        # Selection
        self._is_selection_mode = False
        self._start_point: QPointF | None = None
        self._start_viewport_point = None
        self._temp_selection_item: QGraphicsRectItem | None = None
        self._final_selection_item: QGraphicsRectItem | None = None
        self._debug_rect_items: list[QGraphicsRectItem] = []
        self._saved_region_items: list[QGraphicsRectItem] = []
        self._preview_items: list[QGraphicsItem] = []
        self._is_preview_enabled = False

        # Callbacks
        self.on_selection_committed = None  # Callable[[Rect], None]
        self.on_selection_cleared = None  # Callable[[], None]
        self.get_mapper_func = None  # Callable[[], IPdfCoordinateMapper]
        self.get_text_preview_func = (
            None  # Callable[[str], tuple[TextLayoutResult | None, object | None]]
        )
        self.on_region_selected = None  # Callable[[str], None]
        self.on_region_geometry_changed = None  # Callable[[str, QRectF], None]
        self._region_editing_enabled = True

    def set_region_editing_enabled(self, enabled: bool):
        self._region_editing_enabled = enabled
        for item in self._saved_region_items:
            item.set_editing_enabled(enabled)

        if not enabled:
            self._cancel_selection()

    def set_rendered_page(self, page: RenderedPage):
        if not page:
            self.pixmap_item.setPixmap(QPixmap())
            self.scene.setSceneRect(0, 0, 0, 0)
            self._current_page = None
            return

        self._current_page = page

        # Crear imagen desde bytes crudos. Asegurarse que la referencia de memoria se mantenga viva.
        img = QImage(
            page.samples,
            page.width,
            page.height,
            page.stride,
            QImage.Format_RGBA8888 if page.format == "RGBA8888" else QImage.Format_RGB888,
        )

        pixmap = QPixmap.fromImage(img)
        self.pixmap_item.setPixmap(pixmap)

        # El tamaño de la escena es el tamaño de la imagen renderizada (pixels del pixmap)
        self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        # Centrar el item en el top-left
        self.pixmap_item.setPos(0, 0)

        # Reposicionar el scroll arriba y a la izquierda al cambiar de página
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)

        # Aplicar el zoom actual (puede recalcular fit_width)
        self._apply_transform()

    def set_zoom_mode(self, mode: ZoomMode):
        self._zoom_mode = mode
        self._apply_transform()

    def set_zoom_factor(self, factor: float):
        self._zoom_factor = factor
        self._apply_transform()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recalcular transformaciones que dependen del tamaño del viewport (Fit Width, Fit Page)
        if self._zoom_mode in (ZoomMode.FIT_WIDTH, ZoomMode.FIT_PAGE):
            self._apply_transform()

    def _apply_transform(self):
        if not self._current_page:
            return

        # El render_scale usado para generar la imagen es parte vital del cálculo.
        # Si el usuario quiere ver "100%" (logical Actual Size), y la imagen fue renderizada al 1.5x,
        # entonces el Viewport necesita un scale visual de (1.0 / 1.5) para deshacer el render_scale y mostrarse a 100% físico lógico.

        target_logical_zoom = self._zoom_factor

        if self._zoom_mode == ZoomMode.FIT_WIDTH:
            # Fit Width lógico: Viewport width (con márgenes) dividido por logical_width
            view_w = self.viewport().width() - 20  # margen
            if self._current_page.logical_width > 0:
                target_logical_zoom = view_w / self._current_page.logical_width

        elif self._zoom_mode == ZoomMode.FIT_PAGE:
            view_w = self.viewport().width() - 20
            view_h = self.viewport().height() - 20
            if self._current_page.logical_width > 0 and self._current_page.logical_height > 0:
                zoom_w = view_w / self._current_page.logical_width
                zoom_h = view_h / self._current_page.logical_height
                target_logical_zoom = min(zoom_w, zoom_h)

        elif self._zoom_mode == ZoomMode.ACTUAL_SIZE:
            target_logical_zoom = 1.0

        # target_logical_zoom representa lo que el usuario "siente" (ej: 1.0 = 100%).
        # Pero nuestra imagen (QGraphicsScene) está escalada por `render_scale`.
        # view_zoom * render_scale = target_logical_zoom
        # view_zoom = target_logical_zoom / render_scale

        view_zoom = target_logical_zoom / self._current_page.render_scale

        t = QTransform()
        t.scale(view_zoom, view_zoom)
        self.setTransform(t)

    def set_selection_mode(self, enabled: bool):
        self._is_selection_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.unsetCursor()
            self._cancel_selection()

    def _cancel_selection(self):
        if self._temp_selection_item:
            self.scene.removeItem(self._temp_selection_item)
            self._temp_selection_item = None
        self._start_point = None

    def set_current_selection(self, selection: PdfSelection | None):
        if self._final_selection_item:
            self.scene.removeItem(self._final_selection_item)
            self._final_selection_item = None

        if not selection or not self.get_mapper_func:
            return

        mapper = self.get_mapper_func()
        if not mapper:
            return

        # Round-trip de demostración: tomamos el pdf_rect puro de la selección
        # y lo llevamos a rendered pixel coords usando el mapper
        rendered_rect = mapper.pdf_rect_to_rendered(selection.pdf_rect)

        qrect = QRectF(
            rendered_rect.x0,
            rendered_rect.y0,
            rendered_rect.x1 - rendered_rect.x0,
            rendered_rect.y1 - rendered_rect.y0,
        )

        self._final_selection_item = QGraphicsRectItem(qrect)
        pen = QPen(QColor(0, 120, 215))  # Windows blue
        pen.setWidthF(
            max(1.0, 2.0 / self.transform().m11())
        )  # Stroke thickness que resista el zoom
        self._final_selection_item.setPen(pen)
        self._final_selection_item.setBrush(QBrush(QColor(0, 120, 215, 60)))  # Transparente
        self._final_selection_item.setZValue(3)
        self.scene.addItem(self._final_selection_item)

    def set_preview_mode(self, enabled: bool):
        self._is_preview_enabled = enabled

    def set_saved_regions(self, regions: list[TranslationRegion]):
        for item in self._saved_region_items:
            self.scene.removeItem(item)
        self._saved_region_items.clear()

        for item in self._preview_items:
            self.scene.removeItem(item)
        self._preview_items.clear()

        mapper = self.get_mapper_func() if self.get_mapper_func else None
        if not mapper or not regions:
            return

        for region in regions:
            r_rect = mapper.pdf_rect_to_rendered(region.selection_rect)
            qrect = QRectF(r_rect.x0, r_rect.y0, r_rect.width, r_rect.height)

            page_w = self.pixmap_item.pixmap().width()
            page_h = self.pixmap_item.pixmap().height()

            item = SavedRegionItem(region.id, qrect, page_w, page_h)
            item.update_pen_width(self.transform().m11())

            if self.on_region_selected:
                item.signals.region_selected.connect(self.on_region_selected)
            if self.on_region_geometry_changed:
                item.signals.region_geometry_changed.connect(self.on_region_geometry_changed)

            # Ensure Z-order
            item.setZValue(2)
            item.set_editing_enabled(self._region_editing_enabled)
            self.scene.addItem(item)
            self._saved_region_items.append(item)

            if (
                self._is_preview_enabled
                and region.status == RegionStatus.TRANSLATED
                and region.translated_text
            ):
                layout_result, rendered_preview, overlay_rect_domain, bg_rgb = (
                    self.get_text_preview_func(region.id)
                    if self.get_text_preview_func
                    else (None, None, None, None)
                )
                
                if overlay_rect_domain:
                    r_overlay = mapper.pdf_rect_to_rendered(overlay_rect_domain)
                    effective_qrect = QRectF(r_overlay.x0, r_overlay.y0, r_overlay.width, r_overlay.height)
                else:
                    effective_qrect = qrect
                
                preview_item = TranslationPreviewItem(
                    region_id=region.id,
                    rendered_rect=effective_qrect,
                    layout=layout_result,
                    rendered_preview=rendered_preview,
                    fallback_text=region.translated_text,
                    background_rgb=bg_rgb,
                )
                preview_item.setZValue(1)
                self.scene.addItem(preview_item)
                self._preview_items.append(preview_item)

    def select_saved_region(self, region_id: str | None):
        """Programa la selección visual de una región guardada sin re-emitir on_region_selected."""
        for item in self._saved_region_items:
            # Silenciar temporalmente la señal para evitar loops
            item.signals.blockSignals(True)
            if region_id and item.region_id == region_id:
                item.setSelected(True)
            else:
                item.setSelected(False)
            item.signals.blockSignals(False)

    def set_debug_rects(self, native_rects: list[Rect]):
        """Dibuja rectángulos de debug (fragment bboxes) proyectados desde PDF nativo."""
        for item in self._debug_rect_items:
            self.scene.removeItem(item)
        self._debug_rect_items.clear()

        mapper = self.get_mapper_func() if self.get_mapper_func else None
        if not mapper or not native_rects:
            return

        for n_rect in native_rects:
            r_rect = mapper.pdf_rect_to_rendered(n_rect)
            qrect = QRectF(r_rect.x0, r_rect.y0, r_rect.width, r_rect.height)
            item = QGraphicsRectItem(qrect)

            pen = QPen(QColor(0, 255, 0))  # Green for debug
            pen.setWidthF(max(1.0, 1.0 / self.transform().m11()))
            item.setPen(pen)
            item.setBrush(QBrush(QColor(0, 255, 0, 30)))
            self.scene.addItem(item)
            self._debug_rect_items.append(item)

    def mousePressEvent(self, event):
        if (
            self._is_selection_mode
            and self._region_editing_enabled
            and event.button() == Qt.LeftButton
            and self._current_page
        ):
            pt_scene = self.mapToScene(event.pos())
            # Convert to pixmap item coords
            pt_item = self.pixmap_item.mapFromScene(pt_scene)

            w = self.pixmap_item.pixmap().width()
            h = self.pixmap_item.pixmap().height()

            # Policy: if started outside the rendered image, ignore selection
            if not (0.0 <= pt_item.x() <= w and 0.0 <= pt_item.y() <= h):
                return

            self._start_point = pt_item
            self._start_viewport_point = event.pos()

            if not self._temp_selection_item:
                self._temp_selection_item = QGraphicsRectItem()
                pen = QPen(QColor(255, 0, 0))  # Red temporal
                pen.setStyle(Qt.DashLine)
                pen.setWidthF(max(1.0, 1.0 / self.transform().m11()))
                self._temp_selection_item.setPen(pen)
                self._temp_selection_item.setBrush(QBrush(QColor(255, 0, 0, 40)))
                self.scene.addItem(self._temp_selection_item)
                self._temp_selection_item.setZValue(3)

            self._temp_selection_item.setRect(QRectF(self._start_point, self._start_point))
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_selection_mode and self._start_point and self._temp_selection_item:
            pt_scene = self.mapToScene(event.pos())
            current_point = self.pixmap_item.mapFromScene(pt_scene)

            # Clamp to page bounds
            w = self.pixmap_item.pixmap().width()
            h = self.pixmap_item.pixmap().height()

            cx = max(0.0, min(float(w), current_point.x()))
            cy = max(0.0, min(float(h), current_point.y()))
            clamped_point = QPointF(cx, cy)

            rect = QRectF(self._start_point, clamped_point).normalized()
            self._temp_selection_item.setRect(rect)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_selection_mode and event.button() == Qt.LeftButton and self._start_point:
            if self._temp_selection_item and self._start_viewport_point:
                end_viewport_point = event.pos()

                # Threshold based on viewport pixels to maintain UX consistency across zoom levels
                dx = abs(end_viewport_point.x() - self._start_viewport_point.x())
                dy = abs(end_viewport_point.y() - self._start_viewport_point.y())

                if dx >= 5 or dy >= 5:
                    rect = self._temp_selection_item.rect()
                    domain_rect = Rect(
                        x0=rect.left(), y0=rect.top(), x1=rect.right(), y1=rect.bottom()
                    )
                    if self.on_selection_committed:
                        self.on_selection_committed(domain_rect)

            self._cancel_selection()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._is_selection_mode:
                self._cancel_selection()
                if self.on_selection_cleared:
                    self.on_selection_cleared()
            else:
                # Forward to saved regions so they can cancel drags
                for item in self._saved_region_items:
                    if item.isSelected():
                        item.keyPressEvent(event)
            event.accept()
            return

        super().keyPressEvent(event)

        # El View Model no es actualizado automáticamente por redimensiones de Fit Width.
        # En una arquitectura estricta podríamos avisar al ViewModel del nuevo target_logical_zoom,
        # pero es opcional. Por simplicidad de la Fase 1 lo omitimos o lo delegamos.
