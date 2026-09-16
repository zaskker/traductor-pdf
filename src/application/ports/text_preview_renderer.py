from typing import Protocol

from src.domain.value_objects.layout import RenderedTextPreview
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.render_plan import TextBlockPlan

class ITextPreviewRenderer(Protocol):
    def render_preview(
        self,
        overlay_rect: Rect,
        blocks: tuple[TextBlockPlan, ...],
        render_scale: float,
        background_rgb: tuple[int, int, int] = (255, 255, 255),
    ) -> RenderedTextPreview:
        """
        Renderiza el layout tipográfico final a un raster (samples) neutro,
        empleando exactamente los mismos parámetros que generaron el FIT.
        """
        ...
