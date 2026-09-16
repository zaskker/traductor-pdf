import pymupdf as fitz
import pytest

from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.adapter import PyMuPDFDocument


@pytest.fixture
def dummy_pdf(tmp_path):
    pdf_path = str(tmp_path / "dummy.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=300)
    doc.new_page(width=400, height=300)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_adapter_open_close(dummy_pdf):
    adapter = PyMuPDFDocument()
    assert adapter.get_page_count() == 0

    adapter.open(dummy_pdf)
    assert adapter.get_page_count() == 2

    adapter.close()
    assert adapter.get_page_count() == 0


def test_adapter_render_page(dummy_pdf):
    adapter = PyMuPDFDocument()
    adapter.open(dummy_pdf)

    rendered = adapter.render_page(0, render_scale=1.0)
    assert rendered.page_number == 1
    assert rendered.logical_width == 400
    assert rendered.logical_height == 300
    assert rendered.width > 0
    assert rendered.height > 0
    assert len(rendered.samples) > 0
    assert rendered.format in ("RGB888", "RGBA8888")

    # Probar escala
    rendered_scaled = adapter.render_page(0, render_scale=2.0)
    assert rendered_scaled.width == rendered.width * 2

    adapter.close()


def test_adapter_invalid_file():
    with pytest.raises(Exception):  # noqa: B017
        adapter = PyMuPDFDocument()
        adapter.open("non_existent_file.pdf")


@pytest.mark.parametrize(
    "rotation, render_scale",
    [
        (0, 1.0),
        (90, 1.5),
        (180, 2.0),
        (270, 1.0),
    ],
)
def test_adapter_rotation_mapping(tmp_path, rotation, render_scale):
    # Setup a PDF with rotation
    pdf_path = str(tmp_path / f"rot_{rotation}.pdf")
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.set_rotation(rotation)
    native_rect = fitz.Rect(50, 50, 150, 100)
    page.insert_textbox(native_rect, "Rot", color=(1, 0, 0))
    doc.save(pdf_path)
    doc.close()

    # Use adapter
    adapter = PyMuPDFDocument()
    adapter.open(pdf_path)

    rendered = adapter.render_page(0, render_scale=render_scale)

    # Verify dimensions swap
    if rotation in (90, 270):
        assert rendered.width == int(300 * render_scale)
        assert rendered.height == int(400 * render_scale)
    else:
        assert rendered.width == int(400 * render_scale)
        assert rendered.height == int(300 * render_scale)

    mapper = adapter.get_coordinate_mapper(0, render_scale=render_scale)

    # In the new SAFE-02 contract, PDF space is page.rect space (already cropped and rotated).
    # The native_rect inserted via insert_textbox uses page.rect coordinates too!
    # Wait, insert_textbox with unrotated coordinates might have behaved differently, but page.rect is rotated.
    # Actually, the test inserted text at `native_rect`. Since page was rotated before insertion, `native_rect` was interpreted in `page.rect` space!
    # So the expected rendered rect is just native_rect * render_scale!
    
    expected_rendered = Rect(
        native_rect.x0 * render_scale, native_rect.y0 * render_scale, native_rect.x1 * render_scale, native_rect.y1 * render_scale
    )

    pdf_rect = Rect(native_rect.x0, native_rect.y0, native_rect.x1, native_rect.y1)
    mapped_rendered = mapper.pdf_rect_to_rendered(pdf_rect)

    assert abs(mapped_rendered.x0 - expected_rendered.x0) < 1e-4
    assert abs(mapped_rendered.y0 - expected_rendered.y0) < 1e-4
    assert abs(mapped_rendered.x1 - expected_rendered.x1) < 1e-4
    assert abs(mapped_rendered.y1 - expected_rendered.y1) < 1e-4

    recovered = mapper.rendered_rect_to_pdf(mapped_rendered)
    assert abs(recovered.x0 - pdf_rect.x0) < 1e-4
    assert abs(recovered.y0 - pdf_rect.y0) < 1e-4
    assert abs(recovered.x1 - pdf_rect.x1) < 1e-4
    assert abs(recovered.y1 - pdf_rect.y1) < 1e-4


@pytest.mark.parametrize(
    "rotation, crop_offset, render_scale",
    [
        (0, (50, 100), 1.0),
        (90, (50, 100), 1.5),
    ],
)
def test_adapter_cropbox_mapping(tmp_path, rotation, crop_offset, render_scale):
    # Setup a PDF with rotation and cropbox
    pdf_path = str(tmp_path / "crop.pdf")
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    cx, cy = crop_offset
    page.set_cropbox(fitz.Rect(cx, cy, cx + 500, cy + 600))
    page.set_rotation(rotation)

    # 50, 100 inside the unrotated cropbox -> which means cx+50, cy+100 in native
    native_rect = fitz.Rect(cx + 50, cy + 100, cx + 150, cy + 200)
    page.insert_textbox(native_rect, "Crop", color=(0, 1, 0))
    doc.save(pdf_path)
    doc.close()

    # Use adapter
    adapter = PyMuPDFDocument()
    adapter.open(pdf_path)

    rendered = adapter.render_page(0, render_scale=render_scale)

    if rotation in (90, 270):
        assert rendered.width == int(600 * render_scale)
        assert rendered.height == int(500 * render_scale)
    else:
        assert rendered.width == int(500 * render_scale)
        assert rendered.height == int(600 * render_scale)

    mapper = adapter.get_coordinate_mapper(0, render_scale=render_scale)

    # In the new contract, PDF space is page.rect space.
    # The test inserted text at `native_rect` which was relative to `page.rect`.
    expected_rendered = Rect(
        native_rect.x0 * render_scale, native_rect.y0 * render_scale, native_rect.x1 * render_scale, native_rect.y1 * render_scale
    )

    pdf_rect = Rect(native_rect.x0, native_rect.y0, native_rect.x1, native_rect.y1)
    mapped_rendered = mapper.pdf_rect_to_rendered(pdf_rect)

    assert abs(mapped_rendered.x0 - expected_rendered.x0) < 1e-4
    assert abs(mapped_rendered.y0 - expected_rendered.y0) < 1e-4
    assert abs(mapped_rendered.x1 - expected_rendered.x1) < 1e-4
    assert abs(mapped_rendered.y1 - expected_rendered.y1) < 1e-4

    recovered = mapper.rendered_rect_to_pdf(mapped_rendered)
    assert abs(recovered.x0 - pdf_rect.x0) < 1e-4
    assert abs(recovered.y0 - pdf_rect.y0) < 1e-4
    assert abs(recovered.x1 - pdf_rect.x1) < 1e-4
    assert abs(recovered.y1 - pdf_rect.y1) < 1e-4
