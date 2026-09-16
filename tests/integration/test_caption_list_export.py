"""
Integration test — caption + list item export fixture.
Reproduces the real-world bug:
  Source: "Figure 2.21 – IP while on proxy" + "7. You may now return..."
  Expected: en-dash preserved, 7. inline with text, not split across lines.

Uses REAL SourceFragment, real HtmlTextRenderer, real VectorFormExporter.
No mocks for rendering.
"""

import os
import tempfile

import pymupdf
import pytest

from src.application.dtos.export import (
    ExportRegionSpec,
    ExportRequest,
    ExportTextBlockSpec,
    PdfFingerprint,
)
from src.application.services.block_grouper import group_source_fragments_into_blocks
from src.domain.value_objects.extraction import FragmentGranularity, SourceFragment
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.html_text_renderer import HtmlTextRenderer
from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter


def _make_fragment(text, block_index, line_index, span_index, x0, y0, x1, y1):
    return SourceFragment(
        text=text,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        granularity=FragmentGranularity.SPAN,
        block_index=block_index,
        line_index=line_index,
        span_index=span_index,
        raw_font_name="Helvetica",
        font_size=10.0,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False,
    )


@pytest.fixture(scope="module")
def source_pdf():
    """Create a minimal single-page PDF (200x300 pt) for use as export source."""
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=300)
    # Draw a simple white rectangle to have some content
    page.draw_rect(pymupdf.Rect(10, 40, 190, 200), color=(0, 0, 0))
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    doc.save(path)
    doc.close()
    yield path
    if os.path.exists(path):
        os.unlink(path)


def _compute_fingerprint(path):
    import hashlib

    sha = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
            size += len(chunk)
    doc = pymupdf.open(path)
    pages = doc.page_count
    doc.close()
    return PdfFingerprint(sha256=sha.hexdigest(), size=size, page_count=pages)


class TestCaptionListExport:
    """Tests for Figure 2.21 / Item 7 fixture."""

    def test_en_dash_not_substituted(self, source_pdf):
        """EN DASH must not become '?' in exported PDF."""
        renderer = HtmlTextRenderer()
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=300)
        rect = pymupdf.Rect(10, 40, 190, 100)

        renderer.insert_into_page(
            page,
            rect,
            "Figura 2.21 \u2013 IP mientras está en proxy",
            10.0,
        )
        extracted = page.get_text()
        doc.close()

        assert "\u2013" in extracted, f"EN DASH missing, extracted: {repr(extracted)}"
        assert "?" not in extracted, f"'?' found in extracted text: {repr(extracted)}"

    def test_list_item_7_not_isolated(self, source_pdf):
        """'7.' prefix must appear on the same line as 'Ahora'."""
        renderer = HtmlTextRenderer()
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=300)
        rect = pymupdf.Rect(10, 110, 190, 200)

        renderer.insert_into_page(
            page,
            rect,
            "7. Ahora puede volver, eliminar el proxy y cerrar el navegador web.",
            10.0,
        )
        extracted = page.get_text()
        doc.close()

        lines = [l.strip() for l in extracted.split("\n") if l.strip()]
        # "7." must NOT appear on a line by itself
        assert "7." not in lines, f"Isolated '7.' found. Lines: {lines}"
        # "7." must appear on the same line as the body
        seven_line = next((l for l in lines if "7." in l), None)
        assert seven_line is not None, "Line containing '7.' not found"
        assert "Ahora" in seven_line, (
            f"Expected 'Ahora' on same line as '7.'. Line: {repr(seven_line)}"
        )

    def test_caption_and_list_both_unicode_correct(self, source_pdf):
        """Both caption and list item render without '?' in a single region."""
        renderer = HtmlTextRenderer()
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=300)
        rect = pymupdf.Rect(10, 40, 190, 200)

        text = (
            "Figura 2.21 \u2013 IP mientras está en proxy\n"
            "7. Ahora puede volver, eliminar el proxy y cerrar el navegador web."
        )
        renderer.insert_into_page(page, rect, text, 10.0)
        extracted = page.get_text()
        doc.close()

        assert "\u2013" in extracted
        assert "?" not in extracted
        assert "Figura" in extracted
        assert "7." in extracted

    def test_exported_pdf_contains_unicode(self, source_pdf, tmp_path):
        """VectorFormExporter produces searchable PDF with Unicode intact."""
        dest = str(tmp_path / "exported.pdf")
        fingerprint = _compute_fingerprint(source_pdf)

        region_rect = Rect(10, 40, 190, 200)
        caption_rect = Rect(10, 40, 190, 100)
        item_rect = Rect(10, 110, 190, 200)

        spec = ExportRegionSpec(
            region_id="test-region-1",
            page_number=1,
            pdf_rect=region_rect,
            translated_text="Figura 2.21 \u2013 IP\n7. Ahora puede volver.",
            font_family="notos",
            font_size=10.0,
            background_rgb=(255, 255, 255),
            font_color=(0, 0, 0),
            blocks=(
                ExportTextBlockSpec(
                    rect=caption_rect,
                    translated_text="Figura 2.21 \u2013 IP mientras está en proxy",
                    font_size=10.0,
                ),
                ExportTextBlockSpec(
                    rect=item_rect,
                    translated_text="7. Ahora puede volver, eliminar el proxy y cerrar el navegador web.",
                    font_size=10.0,
                ),
            ),
        )

        request = ExportRequest(
            source_path=source_pdf,
            destination_path=dest,
            expected_fingerprint=fingerprint,
            specs=(spec,),
        )

        exporter = PyMuPDFVectorFormPdfExporter()
        result = exporter.export(request)

        assert os.path.exists(dest)
        doc = pymupdf.open(dest)
        page = doc[0]
        extracted = page.get_text()
        doc.close()

        assert "\u2013" in extracted, f"EN DASH missing. Extracted: {repr(extracted[:300])}"
        assert "?" not in extracted, f"'?' found. Extracted: {repr(extracted[:300])}"
        assert "Figura" in extracted
        assert "7." in extracted


class TestUrlNowrapExport:
    """Tests for URL no-break in export."""

    def test_url_not_split(self, source_pdf, tmp_path):
        dest = str(tmp_path / "url_test.pdf")
        fingerprint = _compute_fingerprint(source_pdf)

        spec = ExportRegionSpec(
            region_id="url-region-1",
            page_number=1,
            pdf_rect=Rect(10, 40, 190, 200),
            translated_text="Navega a https://www.whatismyip.com.",
            font_family="notos",
            font_size=10.0,
            background_rgb=(255, 255, 255),
            font_color=(0, 0, 0),
            blocks=(
                ExportTextBlockSpec(
                    rect=Rect(10, 40, 190, 200),
                    translated_text="Navega a https://www.whatismyip.com.",
                    font_size=10.0,
                ),
            ),
        )

        request = ExportRequest(
            source_path=source_pdf,
            destination_path=dest,
            expected_fingerprint=fingerprint,
            specs=(spec,),
        )

        exporter = PyMuPDFVectorFormPdfExporter()
        exporter.export(request)

        doc = pymupdf.open(dest)
        page = doc[0]
        extracted = page.get_text()
        doc.close()

        lines = [l.strip() for l in extracted.split("\n") if l.strip()]
        # The URL should appear as a single token
        url_found = any("whatismyip.com" in l for l in lines)
        orphan_com = any(l == "com." for l in lines)
        assert url_found, f"URL not found in extracted text. Lines: {lines}"
        assert not orphan_com, f"Orphaned 'com.' line found. Lines: {lines}"
