"""
PyMuPDF text layout engine — Unicode-safe via HtmlTextRenderer.

Uses insert_htmlbox with Noto Sans (pymupdf-fonts, SIL OFL) instead of
insert_textbox + helv. This resolves glyph coverage for EN DASH and all
other Unicode characters lost by Base-14 Helvetica.

The fitting algorithm remains a binary search between min_font_size and
max_font_size, using HtmlTextRenderer.measure_fit() as the oracle.
"""

from __future__ import annotations

import pymupdf

from src.application.ports.text_layout_engine import ITextLayoutEngine
from src.domain.models.enums import FitStatus, TextWrapMode, TextAlignment
from src.domain.value_objects.layout import TextLayoutInput, TextLayoutLine, TextLayoutResult
from src.infrastructure.pdf.html_text_renderer import HtmlTextRenderer

DEFAULT_MIN_FONT_SIZE = 6.0
DEFAULT_MAX_FONT_SIZE = 24.0
SEARCH_TOLERANCE = 0.5
MAX_SEARCH_ITERATIONS = 10


class PyMuPDFTextLayoutEngine(ITextLayoutEngine):
    def __init__(self) -> None:
        self._renderer = HtmlTextRenderer()

    def layout_text(self, input_data: TextLayoutInput) -> TextLayoutResult:
        # Normalise font limits
        min_font = max(DEFAULT_MIN_FONT_SIZE, input_data.min_font_size)
        max_font = max(min_font, input_data.max_font_size)

        fitz_rect = pymupdf.Rect(
            input_data.target_rect.x0,
            input_data.target_rect.y0,
            input_data.target_rect.x1,
            input_data.target_rect.y1,
        )

        # Empty text — trivially fits
        if not input_data.text.strip():
            return TextLayoutResult(font_size=max_font, status=FitStatus.FIT, lines=(), wrap_mode=TextWrapMode.WRAP)

        text = input_data.text

        def _try_fit(wrap_mode: TextWrapMode) -> TextLayoutResult | None:
            # 1. Check minimum font — if doesn't fit -> return None
            structure_str = input_data.structure.name if hasattr(input_data.structure, "name") else str(input_data.structure)
            result_min = self._renderer.measure_fit(fitz_rect, text, min_font, getattr(input_data, "font_color", (0,0,0)), input_data.alignment, wrap_mode, structure_str)
            if result_min.overflow:
                return None

            # 2. Binary search for largest fitting font
            low = min_font
            high = max_font
            best_fit_font = min_font

            for _ in range(MAX_SEARCH_ITERATIONS):
                mid = (low + high) / 2.0
                result = self._renderer.measure_fit(fitz_rect, text, mid, getattr(input_data, "font_color", (0,0,0)), input_data.alignment, wrap_mode, structure_str)

                if not result.overflow:
                    best_fit_font = mid
                    low = mid
                else:
                    high = mid

                if (high - low) < SEARCH_TOLERANCE:
                    break

            lines = self._extract_lines(fitz_rect, text, best_fit_font, input_data.alignment, wrap_mode, structure_str)
            return TextLayoutResult(
                font_size=best_fit_font,
                status=FitStatus.FIT,
                lines=tuple(lines),
                wrap_mode=wrap_mode,
            )

        if input_data.is_single_line_source:
            # Try NOWRAP first
            nowrap_result = _try_fit(TextWrapMode.NOWRAP)
            if nowrap_result:
                return nowrap_result
            # Fallback to WRAP

        wrap_result = _try_fit(TextWrapMode.WRAP)
        if wrap_result:
            return wrap_result

        # Overflow fallback
        return TextLayoutResult(
            font_size=min_font,
            status=FitStatus.OVERFLOW,
            lines=(),
            wrap_mode=TextWrapMode.WRAP
        )

    def _extract_lines(
        self,
        fitz_rect: pymupdf.Rect,
        text: str,
        font_size: float,
        alignment: TextAlignment,
        wrap_mode: TextWrapMode,
        structure: str = "UNKNOWN"
    ) -> list[TextLayoutLine]:
        """
        Render to a temp page and extract line positions via get_text("dict").
        """
        doc = pymupdf.open()
        try:
            page = doc.new_page(
                width=int(fitz_rect.x1) + 100,
                height=int(fitz_rect.y1) + 100,
            )
            self._renderer.insert_into_page(page, fitz_rect, text, font_size, (0,0,0), alignment, wrap_mode, structure)

            lines: list[TextLayoutLine] = []
            extracted = page.get_text("dict")
            for block in extracted.get("blocks", []):
                for line in block.get("lines", []):
                    line_text = "".join(span["text"] for span in line.get("spans", []))
                    y_offset = line["bbox"][1] - fitz_rect.y0
                    lines.append(TextLayoutLine(text=line_text, y_offset=y_offset))
            return lines
        finally:
            doc.close()
