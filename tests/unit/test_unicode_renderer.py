"""
Tests for Unicode glyph coverage and correct rendering via HtmlTextRenderer.
Verifies that Noto Sans (pymupdf-fonts) covers all characters that previously
appeared as '?' with Base-14 Helvetica.
"""

import pymupdf
import pytest

from src.infrastructure.pdf.html_text_renderer import HtmlTextRenderer
from src.domain.models.enums import TextAlignment, TextWrapMode


@pytest.fixture(scope="module")
def renderer():
    return HtmlTextRenderer()


UNICODE_CHARS = [
    ("á", "a-acute"),
    ("é", "e-acute"),
    ("í", "i-acute"),
    ("ó", "o-acute"),
    ("ú", "u-acute"),
    ("ñ", "n-tilde"),
    ("–", "en-dash U+2013"),
    ("—", "em-dash U+2014"),
    ("\u201c", "left-double-quote U+201C"),
    ("\u201d", "right-double-quote U+201D"),
    ("•", "bullet U+2022"),
    ("…", "ellipsis U+2026"),
    ("€", "euro U+20AC"),
]


def _extract_text_via_renderer(renderer: HtmlTextRenderer, text: str) -> str:
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=200)
    rect = pymupdf.Rect(0, 0, 500, 200)
    renderer.insert_into_page(page, rect, text, 12.0)
    extracted = page.get_text()
    doc.close()
    return extracted


@pytest.mark.parametrize("char,name", UNICODE_CHARS)
def test_unicode_char_not_substituted(renderer, char, name):
    """Each Unicode character must appear verbatim in extracted PDF text (no '?')."""
    text = f"Test {char} character"
    extracted = _extract_text_via_renderer(renderer, text)
    assert "?" not in extracted, f"'?' found when rendering {name} ({repr(char)})"
    assert char in extracted, f"Expected {name} ({repr(char)}) in extracted text"


def test_full_unicode_sentence(renderer):
    """Full sentence with mixed Unicode characters passes without '?'."""
    text = "Figura 2.21 \u2013 IP mientras está en proxy"
    extracted = _extract_text_via_renderer(renderer, text)
    assert "?" not in extracted
    assert "\u2013" in extracted  # en-dash preserved
    assert "está" in extracted


def test_url_no_split_across_lines(renderer):
    """URL should not be split across lines when wrapped in white-space:nowrap."""
    text = "Navega a https://www.whatismyip.com para verificar."
    extracted = _extract_text_via_renderer(renderer, text)
    # The URL must appear as a single token — not "whatismyip.\ncom"
    assert "whatismyip.com" in extracted, "URL was split across lines"
    lines = [l.strip() for l in extracted.split("\n") if l.strip()]
    assert not any(l == "com." for l in lines), "Orphaned 'com.' line found"


def test_empty_text_ok(renderer):
    """Empty text should not raise."""
    text = "   "
    result = renderer.measure_fit(pymupdf.Rect(0, 0, 200, 100), text, 12.0)
    # Should not raise and should indicate fit (empty text always fits)


def test_multiple_blocks(renderer):
    """Multiple blocks rendered separately all produce correct Unicode."""
    blocks = [
        "Figura 2.21 \u2013 IP mientras está en proxy",
        "7. Ahora puede volver, eliminar el proxy y cerrar el navegador web.",
    ]
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=400)
    for i, text in enumerate(blocks):
        rect = pymupdf.Rect(0, i * 50, 500, (i + 1) * 50)
        renderer.insert_into_page(page, rect, text, 10.0)
    extracted = page.get_text()
    doc.close()
    assert "\u2013" in extracted
    assert "?" not in extracted
    assert "Figura" in extracted
    assert "7." in extracted
