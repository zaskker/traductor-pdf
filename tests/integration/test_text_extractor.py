import pymupdf as fitz
import pytest

from src.domain.models.enums import ExtractionMethod
from src.domain.value_objects.extraction import FragmentGranularity
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.adapter import PyMuPDFDocument


@pytest.fixture
def pdf_document_path(tmp_path):
    pdf_path = str(tmp_path / "test_extract.pdf")
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)

    # 1. Simple Paragraph
    page.insert_textbox(
        fitz.Rect(50, 50, 350, 150),
        "This is line one.\nThis is line two.\nThis is line three.",
        fontname="helv",
        fontsize=12,
    )

    # 2. Mixed Styles
    page.insert_textbox(
        fitz.Rect(50, 150, 100, 200), "Regular ", fontname="Times-Roman", fontsize=12
    )
    page.insert_textbox(fitz.Rect(100, 150, 150, 200), "Bold ", fontname="Times-Bold", fontsize=12)
    page.insert_textbox(
        fitz.Rect(150, 150, 200, 200), "Italic", fontname="Times-Italic", fontsize=12
    )

    # 3. Two columns
    page.insert_textbox(
        fitz.Rect(50, 200, 150, 300), "Left line 1\nLeft line 2", fontname="helv", fontsize=12
    )
    page.insert_textbox(
        fitz.Rect(200, 200, 300, 300), "Right line 1\nRight line 2", fontname="helv", fontsize=12
    )

    # 4. Phrase for edges
    page.insert_text(fitz.Point(50, 320), "Threat intelligence", fontname="helv", fontsize=12)

    # 5. Span with a targeted word
    page.insert_text(
        fitz.Point(50, 350), "Run sudo apt install nmap now", fontname="helv", fontsize=12
    )

    # Empty space is everywhere else.

    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def pdf_rotated_cropped(tmp_path):
    pdf_path = str(tmp_path / "test_extract_rot.pdf")
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text(fitz.Point(50, 50), "Native Text Rotated", fontname="helv", fontsize=12)
    page.set_rotation(90)
    page.set_cropbox(fitz.Rect(10, 10, 390, 290))
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def extractor(pdf_document_path):
    adapter = PyMuPDFDocument()
    adapter.open(pdf_document_path)
    extractor = adapter.get_text_extractor()
    yield extractor
    adapter.close()


def test_full_paragraph(extractor):
    # Paragraph starts at 50, 50
    # Let's extract the whole paragraph
    sel = Rect(40, 40, 360, 150)
    result = extractor.extract(1, sel)

    assert result.extraction_method == ExtractionMethod.NATIVE_TEXT
    assert len(result.fragments) > 0
    assert result.fragments[0].granularity == FragmentGranularity.SPAN
    assert "This is line one." in result.text
    assert "This is line two." in result.text

    # BBox union test
    assert result.source_bbox is not None
    assert result.source_bbox.x0 >= 40
    assert result.source_bbox.y0 >= 40


def test_partial_line(extractor):
    # Select only the second line (y is roughly around 65)
    sel = Rect(40, 65, 360, 82)
    result = extractor.extract(1, sel)

    assert result.extraction_method == ExtractionMethod.NATIVE_TEXT
    assert "This is line two." in result.text
    assert "line one" not in result.text


def test_mixed_styles(extractor):
    sel = Rect(40, 140, 250, 180)
    result = extractor.extract(1, sel)

    assert len(result.fragments) == 3
    # They should reconstruct to "Regular Bold Italic"
    assert "Regular" in result.text
    assert "Bold" in result.text
    assert "Italic" in result.text

    frag_bold = next(f for f in result.fragments if "Bold" in f.text)
    assert frag_bold.is_bold is True

    frag_italic = next(f for f in result.fragments if "Italic" in f.text)
    assert frag_italic.is_italic is True


def test_two_columns(extractor):
    # Left only
    sel_left = Rect(40, 190, 160, 310)
    result_left = extractor.extract(1, sel_left)
    assert "Left line" in result_left.text
    assert "Right" not in result_left.text

    # Right only
    sel_right = Rect(190, 190, 310, 310)
    result_right = extractor.extract(1, sel_right)
    assert "Right line" in result_right.text
    assert "Left" not in result_right.text

    # Both
    sel_both = Rect(40, 190, 310, 310)
    result_both = extractor.extract(1, sel_both)
    # Our manual reading order sorts by block first, then line.
    # PyMuPDF usually places the left column in block N and the right in block N+1.
    # We should see left column before right column.
    assert "Left line 1\nLeft line 2\n\nRight line 1" in result_both.text


def test_empty_area(extractor):
    sel = Rect(300, 300, 350, 350)
    result = extractor.extract(1, sel)
    assert result.extraction_method == ExtractionMethod.NONE
    assert result.source_bbox is None
    assert len(result.fragments) == 0


def test_word_fallback_sudo(extractor):
    # Select just 'sudo' out of the full span
    sel = Rect(74, 338, 101, 352)
    result = extractor.extract(1, sel)

    assert result.extraction_method == ExtractionMethod.NATIVE_TEXT
    assert len(result.fragments) == 1
    assert result.fragments[0].granularity == FragmentGranularity.WORD
    assert result.text == "sudo"


def test_partial_word_edge(extractor):
    # Exact phrase
    sel_exact = Rect(48, 308, 155, 322)
    res = extractor.extract(1, sel_exact)
    assert "Threat intelligence" in res.text

    # Cut 0.5pt into 'Threat'
    # 'T' starts ~50. Let's start at 50.5
    sel_cut = Rect(50.5, 308, 155, 322)
    res_cut = extractor.extract(1, sel_cut)
    # With SPAN logic and 0.5 center rule, it should still accept the whole span
    assert "Threat intelligence" in res_cut.text

    # Select only 'intelligence'
    sel_intel = Rect(87, 308, 155, 322)
    res_intel = extractor.extract(1, sel_intel)
    assert "intelligence" in res_intel.text


def test_phase2_integration(pdf_rotated_cropped):
    # Roundtrip from rendered coords to PDF coords and extraction
    adapter = PyMuPDFDocument()
    adapter.open(pdf_rotated_cropped)

    # Render at 1.5x scale
    render_scale = 1.5
    mapper = adapter.get_coordinate_mapper(0, render_scale)

    # The text is at (50, 50) logically in original unrotated uncropped page.
    # We rotated 90 degrees.
    # The text "Native Text Rotated" is going to be somewhere else visually.
    # We can just construct a Rect in native space covering it.
    native_rect = Rect(40, 35, 150, 55)

    # Roundtrip check
    rendered = mapper.pdf_rect_to_rendered(native_rect)
    pdf_back = mapper.rendered_rect_to_pdf(rendered)

    extractor = adapter.get_text_extractor()
    result = extractor.extract(1, pdf_back)

    assert "Native Text Rotated" in result.text

    adapter.close()


@pytest.fixture
def pdf_multi_page(tmp_path):
    pdf_path = str(tmp_path / "multi_page.pdf")
    doc = fitz.open()
    # Page 1
    p1 = doc.new_page(width=400, height=400)
    p1.insert_text(fitz.Point(50, 50), "FIRST_PAGE", fontname="helv", fontsize=12)
    # Page 2
    p2 = doc.new_page(width=400, height=400)
    p2.insert_text(fitz.Point(50, 50), "SECOND_PAGE", fontname="helv", fontsize=12)
    # Page 3
    p3 = doc.new_page(width=400, height=400)
    p3.insert_text(fitz.Point(50, 50), "THIRD_PAGE", fontname="helv", fontsize=12)

    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_page_numbering(pdf_multi_page):
    adapter = PyMuPDFDocument()
    adapter.open(pdf_multi_page)
    extractor = adapter.get_text_extractor()

    sel = Rect(40, 40, 200, 100)

    res1 = extractor.extract(1, sel)
    assert "FIRST_PAGE" in res1.text

    res2 = extractor.extract(2, sel)
    assert "SECOND_PAGE" in res2.text

    res3 = extractor.extract(3, sel)
    assert "THIRD_PAGE" in res3.text

    # Invalid pages
    with pytest.raises(ValueError, match="Invalid page_number"):
        extractor.extract(0, sel)

    with pytest.raises(ValueError):  # Should raise out of range
        extractor.extract(4, sel)
    adapter.close()


def test_image_only(tmp_path):
    pdf_path = str(tmp_path / "image_only.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=400)
    doc.save(pdf_path)
    doc.close()
    adapter = PyMuPDFDocument()
    adapter.open(pdf_path)
    extractor = adapter.get_text_extractor()
    res = extractor.extract(1, Rect(0, 0, 400, 400))
    assert res.extraction_method == ExtractionMethod.NONE
    assert len(res.fragments) == 0
    adapter.close()
