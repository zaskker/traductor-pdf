"""
HtmlTextRenderer — shared Unicode-safe text rendering for Preview and Export.

Single source of truth for how translated text is rendered into a PyMuPDF page.
Used by:
  - PyMuPDFTextLayoutEngine (fit detection)
  - PyMuPDFTextPreviewRenderer (raster preview)
  - PyMuPDFVectorFormPdfExporter (vector export overlay)

Rendering path: insert_htmlbox with Noto Sans (pymupdf-fonts, SIL OFL).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

import pymupdf

from src.domain.models.enums import TextAlignment, TextWrapMode

from src.infrastructure.pdf.font_resolver import (
    build_unicode_css_and_archive,
    font_family_name,
)
from src.application.dtos.export import ExportTextBlockSpec

# Detect URLs/paths for no-break wrapping
_URL_RE = re.compile(r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+|[A-Za-z]:\\[^\s<>\"']*)")


@dataclass(frozen=True)
class HtmlRenderResult:
    """Result from a render or fit attempt."""

    remaining_height: float
    """Remaining vertical space after the block. Negative → overflow."""
    scale: float
    """Scale factor applied by insert_htmlbox (1.0 = no scale)."""

    @property
    def fits(self) -> bool:
        return self.remaining_height >= 0 and self.scale >= 1.0

    @property
    def overflow(self) -> bool:
        return not self.fits


def _escape_and_nowrap_urls(text: str) -> str:
    """
    HTML-escape text and wrap detected URLs in <span style='white-space:nowrap'>.
    Preserves safe rendering of < > & in translated content.
    """
    parts = []
    last = 0
    for m in _URL_RE.finditer(text):
        # Escape text before the URL
        parts.append(html.escape(text[last : m.start()]))
        # Wrap the URL itself
        parts.append(f"<span style='white-space:nowrap'>{html.escape(m.group(0))}</span>")
        last = m.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def build_region_html(text: str, alignment: TextAlignment, wrap_mode: TextWrapMode, structure: str = "UNKNOWN") -> str:
    """
    Build HTML body for a block.
    """
    css_classes = ["margin:0", "padding:0"]
    
    if alignment == TextAlignment.CENTER:
        css_classes.append("text-align:center")
    elif alignment == TextAlignment.RIGHT:
        css_classes.append("text-align:right")
    else:
        css_classes.append("text-align:left")
        
    if wrap_mode == TextWrapMode.NOWRAP:
        css_classes.append("white-space:nowrap")
        
    style_str = ";".join(css_classes)

    if structure == "PARAGRAPH":
        # Split by double newline to form multiple paragraphs
        parts = text.split("\n\n")
        escaped_parts = [_escape_and_nowrap_urls(p.strip()) for p in parts if p.strip()]
        return "".join(f"<p style='{style_str}; margin-bottom: 0.5em;'>{p}</p>" for p in escaped_parts)
    elif structure in ("LIST", "LINE_ORIENTED"):
        # Replace single newlines with <br>
        lines = text.split("\n")
        escaped_lines = [_escape_and_nowrap_urls(line) for line in lines]
        inner = "<br>".join(escaped_lines)
        return f"<p style='{style_str}'>{inner}</p>"
    else:
        # Default soft wrap: \n becomes space (let PyMuPDF do the wrapping)
        text = text.replace("\n", " ")
        inner = _escape_and_nowrap_urls(text)
        return f"<p style='{style_str}'>{inner}</p>"


def _make_css(font_family: str, font_size_pt: float, font_color: tuple[int, int, int] = (0, 0, 0), extra_css: str = "") -> str:
    r, g, b = font_color
    return (
        f"body {{ font-family: '{font_family}'; font-size: {font_size_pt:.2f}pt; "
        f"color: rgb({r}, {g}, {b}); margin: 0; padding: 0; }}" + extra_css
    )


class HtmlTextRenderer:
    """
    Shared renderer for Unicode-safe text layout and export.

    Thread-safety: This class is stateless after construction. The Archive and
    CSS are rebuilt per call to avoid cross-thread sharing issues with PyMuPDF
    internal state. The cost is negligible for the number of regions exported.
    """

    def __init__(self) -> None:
        # Validate font is available at construction time and cache it
        try:
            self._font_css, self._archive = build_unicode_css_and_archive()
            self._family = font_family_name()
        except RuntimeError as e:
            raise RuntimeError(
                "HtmlTextRenderer: Unicode font not available. Run: pip install pymupdf-fonts"
            ) from e

    def insert_into_page(
        self,
        page: pymupdf.Page,
        rect: pymupdf.Rect,
        text: str,
        font_size: float,
        font_color: tuple[int, int, int] = (0, 0, 0),
        alignment: TextAlignment = TextAlignment.LEFT,
        wrap_mode: TextWrapMode = TextWrapMode.WRAP,
        structure: str = "UNKNOWN",
        rotate: int = 0,
    ) -> HtmlRenderResult:
        """
        Insert block text into page at rect using insert_htmlbox.

        Returns HtmlRenderResult with remaining height and scale.
        Negative remaining_height means the text overflows the rect.
        """
        body_css = _make_css(self._family, font_size, font_color)
        full_css = self._font_css + body_css

        body_inner = build_region_html(text, alignment, wrap_mode, structure)
        html_content = f"<body>{body_inner}</body>"

        result = page.insert_htmlbox(rect, html_content, css=full_css, archive=self._archive, rotate=rotate)

        # insert_htmlbox returns (remaining_height, scale) tuple
        if isinstance(result, tuple):
            remaining, scale = result
        else:
            # Older API may return scalar
            remaining = float(result)
            scale = 1.0

        return HtmlRenderResult(remaining_height=remaining, scale=scale)

    def render_to_pixmap(
        self,
        rect: pymupdf.Rect,
        text: str,
        font_size: float,
        font_color: tuple[int, int, int],
        background_rgb: tuple[int, int, int],
        render_scale: float,
        alignment: TextAlignment = TextAlignment.LEFT,
        wrap_mode: TextWrapMode = TextWrapMode.WRAP,
        structure: str = "UNKNOWN"
    ) -> pymupdf.Pixmap:
        """
        Render block text to a Pixmap (for Preview use).

        Args:
            rect: target rectangle (PDF coordinates).
            blocks: translated text blocks.
            font_size: font size in pt.
            font_color: text color RGB tuple.
            background_rgb: (R, G, B) 0–255 background fill.
            render_scale: pixmap render scale (e.g. 2.0 for retina).

        Returns:
            pymupdf.Pixmap.

        Raises:
            RuntimeError: if text overflows (should not happen if LayoutEngine
                          already determined FIT).
        """
        doc = pymupdf.open()
        try:
            page = doc.new_page(width=int(rect.x1) + 10, height=int(rect.y1) + 10)
            r, g, b = [c / 255.0 for c in background_rgb]
            page.draw_rect(rect, color=(r, g, b), fill=(r, g, b))

            result = self.insert_into_page(page, rect, text, font_size, font_color, alignment, wrap_mode, structure)

            if result.overflow:
                raise RuntimeError(
                    f"HtmlTextRenderer: text overflow at font_size={font_size:.1f}. "
                    "LayoutEngine should have already determined a FIT size."
                )

            mat = pymupdf.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat, clip=rect)
            return pix
        finally:
            doc.close()

    def render_blocks_to_pixmap(
        self,
        overlay_rect: pymupdf.Rect,
        blocks: tuple,
        background_rgb: tuple[int, int, int],
        render_scale: float,
    ) -> pymupdf.Pixmap:
        """
        Render structured blocks to a Pixmap.
        """
        doc = pymupdf.open()
        try:
            page = doc.new_page(width=int(overlay_rect.x1) + 10, height=int(overlay_rect.y1) + 10)
            r, g, b = [c / 255.0 for c in background_rgb]
            page.draw_rect(overlay_rect, color=(r, g, b), fill=(r, g, b))

            for b_spec in blocks:
                b_rect = pymupdf.Rect(b_spec.rect.x0, b_spec.rect.y0, b_spec.rect.x1, b_spec.rect.y1)
                text = getattr(b_spec, "translated_text", getattr(b_spec, "text", ""))
                structure_val = getattr(b_spec, "structure", "UNKNOWN")
                if hasattr(structure_val, "name"):
                    structure_str = structure_val.name
                else:
                    structure_str = str(structure_val)
                    
                result = self.insert_into_page(
                    page, b_rect, text, b_spec.font_size, getattr(b_spec, "font_color", (0,0,0)), b_spec.alignment, b_spec.wrap_mode, structure_str
                )

                if result.overflow:
                    raise RuntimeError(
                        f"HtmlTextRenderer: text overflow at font_size={b_spec.font_size:.1f} in structured block."
                    )

            mat = pymupdf.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat, clip=overlay_rect)
            return pix
        finally:
            doc.close()

    def measure_fit(
        self,
        rect: pymupdf.Rect,
        text: str,
        font_size: float,
        font_color: tuple[int, int, int] = (0, 0, 0),
        alignment: TextAlignment = TextAlignment.LEFT,
        wrap_mode: TextWrapMode = TextWrapMode.WRAP,
        structure: str = "UNKNOWN"
    ) -> HtmlRenderResult:
        """
        Measure whether block text fits in rect at given font_size.
        Does NOT modify any real page — uses a temporary document.
        """
        doc = pymupdf.open()
        try:
            page = doc.new_page(width=int(rect.x1) + 100, height=int(rect.y1) + 100)
            return self.insert_into_page(page, rect, text, font_size, font_color, alignment, wrap_mode, structure)
        finally:
            doc.close()
