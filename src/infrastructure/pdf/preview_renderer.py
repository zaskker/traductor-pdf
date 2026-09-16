"""
PyMuPDF text preview renderer — Unicode-safe via HtmlTextRenderer.

Uses the same HtmlTextRenderer as the export pipeline to guarantee
Preview == Export parity (Phase 8 rule).
"""

from __future__ import annotations

from src.application.ports.text_preview_renderer import ITextPreviewRenderer
from src.domain.value_objects.layout import RenderedTextPreview
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.render_plan import TextBlockPlan
from src.infrastructure.pdf.html_text_renderer import HtmlTextRenderer


class PyMuPDFTextPreviewRenderer(ITextPreviewRenderer):
    def __init__(self) -> None:
        self._renderer = HtmlTextRenderer()

    def render_preview(
        self,
        overlay_rect: Rect,
        blocks: tuple[TextBlockPlan, ...],
        render_scale: float,
        background_rgb: tuple[int, int, int] = (255, 255, 255),
    ) -> RenderedTextPreview:
        import pymupdf

        fitz_rect = pymupdf.Rect(
            overlay_rect.x0,
            overlay_rect.y0,
            overlay_rect.x1,
            overlay_rect.y1,
        )

        pix = self._renderer.render_blocks_to_pixmap(
            overlay_rect=fitz_rect,
            blocks=blocks,
            background_rgb=background_rgb,
            render_scale=render_scale,
        )

        if pix.stride <= 0:
            raise ValueError("PyMuPDF stride must be greater than 0.")
        if pix.stride < pix.width * pix.n:
            raise ValueError("PyMuPDF stride must be at least width * channels.")
        if len(pix.samples) < pix.height * pix.stride:
            raise ValueError("PyMuPDF samples length is shorter than height * stride.")

        return RenderedTextPreview(
            samples=pix.samples,
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
            channels=pix.n,
            render_scale=render_scale,
        )
