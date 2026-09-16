import logging
from unittest.mock import patch

import fitz
import pytest

from src.application.dtos.export import (
    ExportRegionSpec,
    ExportRequest,
    PdfFingerprint,
)
from src.application.errors.export import (
    ExportError,
    ExportFileError,
    ExportValidationError,
    InvalidExportRequestError,
    SourceFingerprintMismatchError,
)
from src.application.ports.export_progress import ExportCancelledError
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.source_inspector import PyMuPDFPdfSourceInspector
from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter


@pytest.fixture
def exporter():
    return PyMuPDFVectorFormPdfExporter()


@pytest.fixture
def inspector():
    return PyMuPDFPdfSourceInspector()


@pytest.fixture
def rotated_pdf(tmp_path):
    path = str(tmp_path / "rotated.pdf")
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.set_rotation(90)
    page.set_cropbox(fitz.Rect(10, 10, 490, 490))
    doc.save(path)
    doc.close()
    return path


def test_export_rejects_source_equals_destination(exporter, rotated_pdf):
    request = ExportRequest(
        source_path=rotated_pdf,
        destination_path=rotated_pdf,
        expected_fingerprint=PdfFingerprint("a", 1, 1),
        specs=(),
    )
    with pytest.raises(InvalidExportRequestError):
        exporter.export(request)


def test_export_rejects_fingerprint_mismatch(exporter, rotated_pdf, tmp_path):
    request = ExportRequest(
        source_path=rotated_pdf,
        destination_path=str(tmp_path / "out.pdf"),
        expected_fingerprint=PdfFingerprint("fake", 100, 1),
        specs=(
            ExportRegionSpec("r1", 1, Rect(100, 100, 200, 200), "T", "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )
    with pytest.raises(SourceFingerprintMismatchError):
        exporter.export(request)


def test_export_fails_cleanly_if_source_disappears(exporter, inspector, rotated_pdf, tmp_path):
    import os

    dest_path = str(tmp_path / "out.pdf")
    inspection = inspector.inspect(rotated_pdf)
    request = ExportRequest(
        source_path=rotated_pdf,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec("r1", 1, Rect(100, 100, 200, 200), "T", "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )

    # Delete source file before export
    os.unlink(rotated_pdf)

    with pytest.raises(ExportFileError):
        exporter.export(request)


def test_successful_export_atomic_workflow(exporter, inspector, rotated_pdf, tmp_path):
    dest_path = str(tmp_path / "dest.pdf")
    inspection = inspector.inspect(rotated_pdf)

    request = ExportRequest(
        source_path=rotated_pdf,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec(
                region_id="r1",
                page_number=1,
                pdf_rect=Rect(50, 50, 150, 150),
                translated_text="Hola Mundo",
                font_family="helv",
                font_size=12.0,
                font_color=(0, 0, 0),
                background_rgb=(255, 255, 255),
            ),
        ),
    )

    result = exporter.export(request)
    assert result.destination_path == dest_path

    # Check geometry preservation
    with fitz.open(dest_path) as doc:
        page = doc[0]
        assert page.rotation == 90
        assert page.cropbox == fitz.Rect(10, 10, 490, 490)
        assert page.mediabox == fitz.Rect(0, 0, 500, 500)
        assert "Hola Mundo" in page.get_text()


@patch("os.replace")
@patch("os.unlink")
def test_export_safe_cleanup_on_error(
    mock_unlink, mock_replace, exporter, inspector, rotated_pdf, tmp_path, caplog
):
    # Setup mock to fail os.replace (e.g. permission denied)
    mock_replace.side_effect = PermissionError("Cannot replace file")
    # Setup mock to also fail os.unlink during cleanup
    mock_unlink.side_effect = PermissionError("Cannot delete temp file")

    dest_path = str(tmp_path / "dest.pdf")
    inspection = inspector.inspect(rotated_pdf)

    request = ExportRequest(
        source_path=rotated_pdf,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(50, 50, 150, 150), "Test", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ExportFileError) as exc_info:
            exporter.export(request)

        assert "Cannot replace file" in str(exc_info.value)
        assert exc_info.value.cleanup_failed is True
        assert exc_info.value.temporary_path is not None
        assert "tmp.pdf" in exc_info.value.temporary_path

    # Unlink should have been called (cleaning up .tmp.pdf)
    mock_unlink.assert_called_once()

    # But it shouldn't have raised the second PermissionError to crash the program.
    # The warning should be logged.
    assert any("Failed to clean up temporary file" in record.message for record in caplog.records)


@patch("os.unlink")
def test_export_cancel_cleanup_failure(
    mock_unlink, exporter, inspector, rotated_pdf, tmp_path, caplog
):
    # Setup mock to fail os.unlink during cleanup
    mock_unlink.side_effect = PermissionError("Cannot delete temp file")

    dest_path = str(tmp_path / "dest.pdf")
    inspection = inspector.inspect(rotated_pdf)

    request = ExportRequest(
        source_path=rotated_pdf,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(50, 50, 150, 150), "Test", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    class MockContext:
        def __init__(self):
            class MockToken:
                def __init__(self):
                    self.calls = 0

                def throw_if_cancelled(self):
                    self.calls += 1
                    if self.calls > 5:
                        raise ExportCancelledError("Cancelled by user")

            self.cancellation_token = MockToken()
            self.observer = None

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ExportCancelledError) as exc_info:
            exporter.export(request, context=MockContext())

        assert exc_info.value.cleanup_failed is True
        assert exc_info.value.temporary_path is not None
        assert "tmp.pdf" in exc_info.value.temporary_path

    # Unlink should have been called (cleaning up .tmp.pdf)
    mock_unlink.assert_called_once()
    assert any("Failed to clean up temporary file" in record.message for record in caplog.records)


def test_export_text_validation(exporter, inspector, tmp_path):
    path = str(tmp_path / "plain.pdf")
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text((100, 100), "Original Text")
    doc.save(path)
    doc.close()

    inspection = inspector.inspect(path)
    dest_path = str(tmp_path / "out.pdf")

    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(100, 100, 200, 200), "New Text", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    result = exporter.export(request)
    assert result.exported_regions == 1

    # Check that text is validated
    with fitz.open(dest_path) as doc:
        assert "New Text" in doc[0].get_text()


def test_export_rejects_out_of_bounds_region(exporter, inspector, tmp_path):
    path = str(tmp_path / "plain.pdf")
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text((100, 100), "Original Text")
    doc.save(path)
    doc.close()

    inspection = inspector.inspect(path)
    dest_path = str(tmp_path / "out.pdf")

    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(600, 600, 700, 700), "New Text", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    with pytest.raises(InvalidExportRequestError, match="does not intersect visible page"):
        exporter.export(request)


def test_export_page_matrix(exporter, inspector, tmp_path):
    path = str(tmp_path / "matrix.pdf")
    doc = fitz.open()

    # 3 pages
    for i in range(3):
        p = doc.new_page(width=500, height=500)
        p.insert_text((100, 100), f"Page {i + 1}")

    doc.save(path)

    doc.close()

    inspection = inspector.inspect(path)
    dest_path = str(tmp_path / "out_matrix.pdf")

    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(100, 100, 200, 200), "T1", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
            ExportRegionSpec(
                "r2", 2, Rect(100, 100, 200, 200), "T2", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
            ExportRegionSpec(
                "r3", 3, Rect(100, 100, 200, 200), "T3", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    result = exporter.export(request)
    assert result.exported_regions == 3
    assert result.pages_touched == (1, 2, 3)

    with fitz.open(dest_path) as doc:
        assert doc.page_count == 3
        assert "T1" in doc[0].get_text()
        assert "T2" in doc[1].get_text()
        assert "T3" in doc[2].get_text()


def test_export_rotation_cropbox_preservation(exporter, inspector, tmp_path):
    path = str(tmp_path / "rot_crop.pdf")
    doc = fitz.open()

    rotations = [0, 90, 180, 270]
    # 4 pages with different rotations and asymmetric cropboxes
    for i, rot in enumerate(rotations):
        p = doc.new_page(width=500, height=500)
        p.set_rotation(rot)
        p.set_cropbox(fitz.Rect(10 * (i + 1), 20 * (i + 1), 400 - 10 * i, 450 - 20 * i))
        p.insert_text((150, 150), f"R{rot}")

    doc.save(path)

    doc.close()

    inspection = inspector.inspect(path)
    dest_path = str(tmp_path / "out_rot_crop.pdf")

    # We insert into each page
    specs = []
    for i in range(4):
        specs.append(
            ExportRegionSpec(
                f"r{i + 1}",
                i + 1,
                Rect(100, 100, 200, 200),
                f"NewR{rotations[i]}",
                "helv",
                12.0, (0, 0, 0), (255, 255, 255),
            )
        )

    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=tuple(specs),
    )

    result = exporter.export(request)
    assert result.exported_regions == 4

    # Verify geometries
    with fitz.open(dest_path) as doc:
        for i, rot in enumerate(rotations):
            p = doc[i]
            assert p.rotation == rot
            assert p.cropbox == fitz.Rect(10 * (i + 1), 20 * (i + 1), 400 - 10 * i, 450 - 20 * i)
            assert f"NewR{rot}" in p.get_text()


def test_export_uuid_collision(exporter, inspector, tmp_path):
    path = str(tmp_path / "plain.pdf")
    doc = fitz.open()
    doc.new_page(width=500, height=500)
    doc.save(path)
    doc.close()

    dest_path = str(tmp_path / "out.pdf")

    # Mock uuid to return a specific UUID
    fixed_uuid = "12345678123456781234567812345678"

    import os

    collision_path = os.path.join(str(tmp_path), f".out.pdf.{fixed_uuid}.tmp.pdf")
    # Pre-create the file to simulate collision
    with open(collision_path, "wb") as f:
        f.write(b"collision")

    inspection = inspector.inspect(path)
    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec("r1", 1, Rect(10, 10, 20, 20), "T", "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )

    with patch("uuid.uuid4") as mock_uuid:
        import uuid

        mock_uuid.return_value = uuid.UUID(fixed_uuid)
        with pytest.raises(ExportFileError, match="already exists"):
            exporter.export(request)


def test_export_multiple_regions_non_overlapping_stress(exporter, inspector, tmp_path):
    path = str(tmp_path / "stress.pdf")
    doc = fitz.open()
    # 5 pages
    for _ in range(5):
        doc.new_page(width=500, height=500)
    doc.save(path)
    doc.close()

    inspection = inspector.inspect(path)
    dest_path = str(tmp_path / "out_stress.pdf")

    # 100 regions, 20 per page
    specs = []
    for p_num in range(1, 6):
        for r_num in range(20):
            specs.append(
                ExportRegionSpec(
                    f"r_{p_num}_{r_num}",
                    p_num,
                    Rect(10, 25 * r_num, 210, 25 * r_num + 20),
                    f"T_{p_num}_{r_num}",
                    "helv",
                    10.0, (0, 0, 0), (255, 255, 255),
                )
            )

    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=tuple(specs),
    )

    result = exporter.export(request)
    assert result.exported_regions == 100
    assert result.pages_touched == (1, 2, 3, 4, 5)


def test_export_rollback_matrix(exporter, inspector, tmp_path):
    path = str(tmp_path / "rollback.pdf")
    doc = fitz.open()
    doc.new_page(width=500, height=500)
    doc.save(path)
    doc.close()

    dest_path = str(tmp_path / "out_rollback.pdf")
    inspection = inspector.inspect(path)
    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec("r1", 1, Rect(10, 10, 50, 50), "Test", "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )

    # 1. HtmlTextRenderer block overflow
    from src.infrastructure.pdf.html_text_renderer import HtmlRenderResult

    with patch(
        "src.infrastructure.pdf.vector_form_exporter.HtmlTextRenderer.insert_into_page",
        return_value=HtmlRenderResult(-1.0, 1.0),
    ):
        with pytest.raises(ExportValidationError, match="HtmlTextRenderer overflow"):
            exporter.export(request)

    # 2. show_pdf_page raises
    with patch("fitz.Page.show_pdf_page", side_effect=Exception("mocked show failed")):
        with pytest.raises(ExportError, match="mocked show failed"):
            exporter.export(request)

    # 3. doc.save raises
    with patch("fitz.Document.save", side_effect=Exception("mocked save failed")):
        with pytest.raises(ExportFileError, match="mocked save failed"):
            exporter.export(request)

    # 4. Source mutated during export
    # We patch fitz.Document.save to modify the source file before saving temp
    original_save = fitz.Document.save

    def mutating_save(self, *args, **kwargs):
        # Mutate source
        with open(path, "ab") as f:
            f.write(b"junk")
        return original_save(self, *args, **kwargs)

    with patch("fitz.Document.save", side_effect=mutating_save, autospec=True):
        with pytest.raises(SourceFingerprintMismatchError, match="Source file was mutated"):
            exporter.export(request)


def test_select_validation_tokens():
    func = PyMuPDFVectorFormPdfExporter._select_validation_tokens

    # normal sentence
    assert func("Hola") == ("Hola",)

    # Unicode Spanish
    assert func("¿Configuración válida?") == ("Configuración", "válida")

    # URL-only
    assert func("https://example.com/docs") == ("https", "example")

    # Windows path-only
    assert func(r"C:\Tools\app.exe") == ("Tools",)

    # CLI flag-only
    assert func("--verbose") == ("verbose",)

    # explicit newlines
    assert func("Line1\nLine2") == ("Line1", "Line2")

    # mixed prose + URL
    assert func("Visite https://example.com/docs") == ("Visite", "example")

    # mixed prose + path
    assert func(r"Ejecutar C:\Tools\app.exe") == ("Ejecutar", "Ejecutar") or func(
        r"Ejecutar C:\Tools\app.exe"
    ) == ("Ejecutar", "Tools")


@pytest.mark.parametrize(
    "text", ["https://example.com/docs", r"C:\Tools\app.exe", "--verbose", "¿Configuración válida?"]
)
def test_export_real_token_validation(exporter, inspector, tmp_path, text):
    path = str(tmp_path / "tokens.pdf")
    doc = fitz.open()
    doc.new_page(width=500, height=500)
    doc.save(path)
    doc.close()

    dest_path = str(tmp_path / "out_tokens.pdf")
    inspection = inspector.inspect(path)
    request = ExportRequest(
        source_path=path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec("r1", 1, Rect(10, 10, 200, 100), text, "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )

    result = exporter.export(request)
    assert result.exported_regions == 1


def test_export_rollback_existing_destination(exporter, inspector, tmp_path):
    # 1. Create a source PDF
    src_path = str(tmp_path / "rollback_dest_src.pdf")
    doc = fitz.open()
    doc.new_page(width=500, height=500)
    doc.save(src_path)
    doc.close()

    # 2. Create an existing destination file with known bytes
    dest_path = str(tmp_path / "rollback_dest.pdf")
    with open(dest_path, "wb") as f:
        f.write(b"PRE_EXISTING_DESTINATION_BYTES")

    inspection = inspector.inspect(src_path)
    request = ExportRequest(
        source_path=src_path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(
            ExportRegionSpec("r1", 1, Rect(10, 10, 50, 50), "Test", "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )

    # 3. Force os.replace to fail
    with patch("os.replace", side_effect=PermissionError("mocked replace failure")):
        with pytest.raises(ExportError, match="mocked replace failure"):
            exporter.export(request)

    # 4. Verify destination bytes were NOT modified
    with open(dest_path, "rb") as f:
        assert f.read() == b"PRE_EXISTING_DESTINATION_BYTES"


def test_export_parity_white(exporter, inspector, tmp_path):
    from src.domain.value_objects.layout import TextLayoutInput
    from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine
    from src.infrastructure.pdf.preview_renderer import PyMuPDFTextPreviewRenderer

    # 1. Create a white PDF
    src_path = str(tmp_path / "white_src.pdf")
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(1, 1, 1), fill=(1, 1, 1))
    page.insert_textbox(fitz.Rect(50, 50, 250, 150), "Original English Text")
    doc.save(src_path)
    doc.close()

    rect = Rect(50, 50, 250, 150)
    text = "Parity target text"

    # 2. Get optimal layout
    engine = PyMuPDFTextLayoutEngine()
    layout_input = TextLayoutInput(
        text=text, target_rect=rect, font_family="helv", min_font_size=8.0, max_font_size=32.0
    )
    layout = engine.layout_text(layout_input)

    # 3. Generate preview reference
    from src.application.dtos.export import ExportTextBlockSpec
    from src.domain.models.enums import TextAlignment
    
    renderer = PyMuPDFTextPreviewRenderer()
    
    blocks = (
        ExportTextBlockSpec(
            rect=rect,
            translated_text=text,
            font_size=layout.font_size,
            alignment=TextAlignment.LEFT,
            wrap_mode=layout.wrap_mode
        ),
    )
    preview = renderer.render_preview(
        rect, blocks, render_scale=2.0, background_rgb=(255, 255, 255)
    )

    # 4. Export
    dest_path = str(tmp_path / "white_dest.pdf")
    inspection = inspector.inspect(src_path)
    req = ExportRequest(
        source_path=src_path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(ExportRegionSpec("r1", 1, rect, text, "helv", layout.font_size, (0, 0, 0), (255, 255, 255), blocks),),
    )
    exporter.export(req)

    # 5. Compare pixels
    out_doc = fitz.open(dest_path)
    mat = fitz.Matrix(2.0, 2.0)
    out_pix = out_doc[0].get_pixmap(matrix=mat, clip=fitz.Rect(50, 50, 250, 150))
    out_doc.close()

    assert out_pix.width == preview.width
    assert out_pix.height == preview.height
    assert out_pix.n == preview.channels

    # Calculate pixel difference
    s1 = preview.samples
    s2 = out_pix.samples

    changed = 0
    total = preview.width * preview.height
    n = preview.channels

    for i in range(total):
        idx = i * n
        diff = sum(abs(s1[idx + c] - s2[idx + c]) for c in range(3))
        if diff > 0:
            changed += 1

    changed_ratio = changed / total
    assert changed_ratio == 0.0, f"White parity failed, changed_ratio={changed_ratio}"


def test_export_parity_gray_end_to_end(exporter, inspector, tmp_path):
    from src.application.dtos.export import BackgroundAnalysisRequest, BackgroundClassification
    from src.domain.value_objects.layout import TextLayoutInput
    from src.infrastructure.pdf.background_analyzer import PyMuPDFRegionBackgroundAnalyzer
    from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine
    from src.infrastructure.pdf.preview_renderer import PyMuPDFTextPreviewRenderer

    # 1. Create a gray PDF
    src_path = str(tmp_path / "gray_src.pdf")
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
    doc.save(src_path)
    doc.close()

    rect = Rect(50, 50, 250, 150)
    text = "Gray Parity text"

    # 2. Analyze background
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    bg_req = BackgroundAnalysisRequest("r1", 1, rect, ())
    bg_res = analyzer.analyze_many(src_path, (bg_req,))[0]

    assert bg_res.classification == BackgroundClassification.UNIFORM_COLOR
    detected_rgb = bg_res.background_rgb

    # 3. Get layout
    engine = PyMuPDFTextLayoutEngine()
    layout_input = TextLayoutInput(
        text=text, target_rect=rect, font_family="helv", min_font_size=8.0, max_font_size=32.0
    )
    layout = engine.layout_text(layout_input)

    # 4. Generate preview with detected RGB
    from src.application.dtos.export import ExportTextBlockSpec
    from src.domain.models.enums import TextAlignment
    
    renderer = PyMuPDFTextPreviewRenderer()
    blocks = (
        ExportTextBlockSpec(
            rect=rect,
            translated_text=text,
            font_size=layout.font_size,
            alignment=TextAlignment.LEFT,
            wrap_mode=layout.wrap_mode
        ),
    )
    
    preview = renderer.render_preview(
        rect, blocks, render_scale=2.0, background_rgb=detected_rgb
    )

    # 5. Export
    dest_path = str(tmp_path / "gray_dest.pdf")
    inspection = inspector.inspect(src_path)
    req = ExportRequest(
        source_path=src_path,
        destination_path=dest_path,
        expected_fingerprint=inspection.fingerprint,
        specs=(ExportRegionSpec("r1", 1, rect, text, "helv", layout.font_size, (0, 0, 0), detected_rgb, blocks),),
    )
    exporter.export(req)

    # 6. Compare pixels
    out_doc = fitz.open(dest_path)
    mat = fitz.Matrix(2.0, 2.0)
    out_pix = out_doc[0].get_pixmap(matrix=mat, clip=fitz.Rect(50, 50, 250, 150))
    out_doc.close()

    assert out_pix.width == preview.width
    assert out_pix.height == preview.height
    assert out_pix.n == preview.channels

    # Calculate pixel difference
    s1 = preview.samples
    s2 = out_pix.samples

    changed = 0
    total = preview.width * preview.height
    n = preview.channels

    for i in range(total):
        idx = i * n
        diff = sum(abs(s1[idx + c] - s2[idx + c]) for c in range(3))
        if diff > 0:
            changed += 1

    changed_ratio = changed / total
    assert changed_ratio == 0.0, f"Gray parity failed, changed_ratio={changed_ratio}"
