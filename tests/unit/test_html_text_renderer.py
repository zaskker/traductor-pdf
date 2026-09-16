"""
Unit tests for HtmlTextRenderer.
Tests measure_fit, insert_into_page, render_to_pixmap, and URL nowrap.
"""

import pytest
import pymupdf

from src.domain.models.enums import TextAlignment, TextWrapMode
from src.infrastructure.pdf.html_text_renderer import (
    HtmlTextRenderer,
    HtmlRenderResult,
    _escape_and_nowrap_urls,
    build_region_html,
)


@pytest.fixture(scope="module")
def renderer():
    return HtmlTextRenderer()


# ---------------------------------------------------------------------------
# _escape_and_nowrap_urls
# ---------------------------------------------------------------------------


class TestEscapeAndNowrapUrls:
    def test_plain_text_escaped(self):
        out = _escape_and_nowrap_urls("Hello <world> & 'foo'")
        assert "<world>" not in out
        assert "&lt;world&gt;" in out
        assert "&amp;" in out

    def test_url_wrapped(self):
        out = _escape_and_nowrap_urls("See https://www.example.com for info.")
        assert "white-space:nowrap" in out
        assert "https://www.example.com" in out

    def test_no_url_no_nowrap(self):
        out = _escape_and_nowrap_urls("Normal sentence without URL.")
        assert "nowrap" not in out

    def test_multiple_urls_wrapped(self):
        out = _escape_and_nowrap_urls("See http://a.com and https://b.com for details.")
        assert out.count("nowrap") == 2

    def test_en_dash_passthrough(self):
        """En-dash is a normal character, not a URL — should be escaped but present."""
        out = _escape_and_nowrap_urls("Figure 2.21 \u2013 IP")
        assert "\u2013" in out or "&#x2013;" in out or "–" in out


# ---------------------------------------------------------------------------
# build_region_html
# ---------------------------------------------------------------------------


class TestBuildRegionHtml:
    def test_single_block(self):
        html = build_region_html("Hello world", TextAlignment.LEFT, TextWrapMode.WRAP)
        assert "<p" in html
        assert "Hello world" in html



    def test_html_chars_escaped(self):
        html = build_region_html("<script>alert('XSS')</script>", TextAlignment.LEFT, TextWrapMode.WRAP)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# measure_fit
# ---------------------------------------------------------------------------


class TestMeasureFit:
    def test_short_text_fits_large_rect(self, renderer):
        rect = pymupdf.Rect(0, 0, 400, 200)
        result = renderer.measure_fit(rect, "Short text", 12.0)
        assert isinstance(result, HtmlRenderResult)
        assert result.fits

    def test_large_text_overflows_tiny_rect(self, renderer):
        rect = pymupdf.Rect(0, 0, 10, 5)
        result = renderer.measure_fit(
            rect,
            "This is a very long text that cannot possibly fit in a 10x5 pt rect at any reasonable font size",
            20.0,
        )
        assert result.overflow

    def test_unicode_text_fits(self, renderer):
        rect = pymupdf.Rect(0, 0, 300, 100)
        result = renderer.measure_fit(rect, "Figura 2.21 \u2013 IP mientras está en proxy", 12.0)
        assert result.fits


# ---------------------------------------------------------------------------
# insert_into_page
# ---------------------------------------------------------------------------


class TestInsertIntoPage:
    def test_extract_en_dash_from_inserted_text(self, renderer):
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=200)
        rect = pymupdf.Rect(0, 0, 400, 200)
        renderer.insert_into_page(page, rect, "Figura 2.21 \u2013 IP", 12.0)
        extracted = page.get_text()
        doc.close()
        assert "\u2013" in extracted
        assert "?" not in extracted

    def test_url_intact_in_extracted_text(self, renderer):
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=200)
        rect = pymupdf.Rect(0, 0, 400, 200)
        renderer.insert_into_page(
            page, rect, "Navega a https://www.whatismyip.com para verificar.", 10.0
        )
        extracted = page.get_text()
        doc.close()
        assert "whatismyip.com" in extracted

    def test_multi_block_both_extracted(self, renderer):
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=400)
        rect1 = pymupdf.Rect(0, 0, 400, 200)
        rect2 = pymupdf.Rect(0, 200, 400, 400)
        renderer.insert_into_page(page, rect1, "Figura 2.21 \u2013 IP mientras está en proxy", 10.0)
        renderer.insert_into_page(page, rect2, "7. Ahora puede volver, eliminar el proxy y cerrar el navegador web.", 10.0)
        extracted = page.get_text()
        doc.close()
        assert "\u2013" in extracted
        assert "Figura" in extracted
        assert "7." in extracted
        assert "?" not in extracted


# ---------------------------------------------------------------------------
# render_to_pixmap
# ---------------------------------------------------------------------------


class TestRenderToPixmap:
    def test_pixmap_dimensions(self, renderer):
        rect = pymupdf.Rect(0, 0, 200, 100)
        pix = renderer.render_to_pixmap(rect, "Hello", 12.0, (0, 0, 0), (255, 255, 255), 1.0)
        assert pix.width == 200
        assert pix.height == 100
        assert pix.n == 3

    def test_pixmap_with_scale(self, renderer):
        rect = pymupdf.Rect(0, 0, 200, 100)
        pix = renderer.render_to_pixmap(rect, "Hello", 12.0, (0, 0, 0), (255, 255, 255), 2.0)
        assert pix.width == 400
        assert pix.height == 200

    def test_pixmap_overflow_raises(self, renderer):
        rect = pymupdf.Rect(0, 0, 5, 5)
        with pytest.raises(RuntimeError, match="overflow"):
            renderer.render_to_pixmap(
                rect,
                "This text is too long to fit in 5x5 at 20pt",
                20.0,
                (0, 0, 0),
                (255, 255, 255),
                1.0,
            )

# ---------------------------------------------------------------------------
# RENDER-03 Semantic Structure
# ---------------------------------------------------------------------------

class TestRender03SemanticStructure:
    def test_paragraph_structure_splits_on_double_newline(self):
        text = "First paragraph\n\nSecond paragraph"
        html = build_region_html(text, TextAlignment.LEFT, TextWrapMode.WRAP, "PARAGRAPH")
        assert "<p " in html
        assert "First paragraph</p>" in html
        assert "Second paragraph</p>" in html
        assert html.count("<p ") == 2

    def test_list_structure_uses_br_for_single_newline(self):
        text = "1. Item 1\n2. Item 2"
        html = build_region_html(text, TextAlignment.LEFT, TextWrapMode.WRAP, "LIST")
        assert "<p " in html
        assert "1. Item 1<br>2. Item 2</p>" in html
        assert html.count("<p ") == 1

    def test_line_oriented_structure_uses_br_for_single_newline(self):
        text = "Line 1\nLine 2"
        html = build_region_html(text, TextAlignment.LEFT, TextWrapMode.WRAP, "LINE_ORIENTED")
        assert "<p " in html
        assert "Line 1<br>Line 2</p>" in html
        assert html.count("<p ") == 1

    def test_unknown_structure_replaces_newline_with_space(self):
        text = "Part 1\nPart 2"
        html = build_region_html(text, TextAlignment.LEFT, TextWrapMode.WRAP, "UNKNOWN")
        assert "<p " in html
        assert "Part 1 Part 2</p>" in html
        assert "<br>" not in html
        assert html.count("<p ") == 1
