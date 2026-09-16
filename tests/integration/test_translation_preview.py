from unittest.mock import MagicMock
from src.domain.models.project import Project
from datetime import datetime, UTC
from datetime import UTC, datetime

import pymupdf as fitz
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from src.application.services.pdf_viewer_service import PdfViewerService
from src.domain.models.enums import RegionStatus
from src.domain.models.project import Project
from src.domain.value_objects.extraction import (
    ExtractionMethod,
    FragmentGranularity,
    SourceFragment,
    TextExtractionResult,
)
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.adapter import PyMuPDFDocument
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import (
    SqliteProjectRepository,
    SqliteTranslationRegionRepository,
)
from src.infrastructure.translation.fake_engine import FakeTranslationEngine
from src.ui.components.pdf_view_widget import PdfViewWidget
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel, ZoomMode


class MockExtractionService:
    def extract_from_selection(self, selection):
        frag = SourceFragment(
            text="Mock text",
            bbox=selection.pdf_rect,
            granularity=FragmentGranularity.WORD,
            block_index=0,
            line_index=0,
            span_index=0,
            raw_font_name="Arial",
            font_size=10.0,
            font_color="#000",
            font_flags_raw=0,
            is_bold=False,
            is_italic=False,
            is_serif=False,
            is_monospace=False,
        )
        return TextExtractionResult(
            page_number=selection.page_number,
            selection_rect=selection.pdf_rect,
            source_bbox=selection.pdf_rect,
            text="Mock text",
            fragments=(frag,),
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            warnings=(),
        )


class MockProjectService:
    def __init__(self, repo, db):
        self.region_repo = repo
        self.db = db

    def update_last_viewed_page(self, project_id, page_number):
        pass

    def load_project_by_uuid(self, project_id):
        pass

    def discover_or_create_project(self, file_path, page_count):
        project = Project(
            "p1", "Test", "path", "sha", 100, 10, 1, datetime.now(UTC), datetime.now(UTC)
        )
        return project, "test.sqlite"

    def check_project_locked(self, proj, file_path, page_count):
        return False


@pytest.fixture
def qapp_instance():
    import sys

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def pdf_env(tmp_path, qapp_instance):
    db_path = str(tmp_path / "test.sqlite")
    db = Database(db_path)
    db.init_schema()

    proj_repo = SqliteProjectRepository(db)
    repo = SqliteTranslationRegionRepository(db)

    now = datetime.now(UTC)
    project = Project("p1", "Test", "path", "sha", 100, 10, 1, now, now)
    proj_repo.save(project)

    pdf_service = PdfViewerService(PyMuPDFDocument())

    viewmodel = PdfViewerViewModel(
        service=pdf_service,
        extraction_service=MockExtractionService(),
        project_service=MockProjectService(repo, db),
        translation_engine=FakeTranslationEngine(),
    )
    viewmodel._current_project = project

    widget = PdfViewWidget()
    widget.get_mapper_func = viewmodel.get_mapper
    viewmodel.saved_regions_changed.connect(widget.set_saved_regions)
    viewmodel.preview_toggled.connect(widget.set_preview_mode)
    viewmodel.page_rendered.connect(widget.set_rendered_page)
    viewmodel.zoom_mode_changed.connect(widget.set_zoom_mode)
    viewmodel.zoom_factor_changed.connect(widget.set_zoom_factor)
    widget.get_text_layout_func = viewmodel.get_text_layout

    return tmp_path, db, repo, viewmodel, widget


@pytest.mark.parametrize(
    "rotation, cropbox, native_rect",
    [
        (0, None, fitz.Rect(10, 10, 110, 110)),
        (90, None, fitz.Rect(10, 10, 110, 110)),
        (180, None, fitz.Rect(10, 10, 110, 110)),
        (270, None, fitz.Rect(10, 10, 110, 110)),
        (0, fitz.Rect(50, 50, 550, 650), fitz.Rect(100, 100, 200, 200)),
    ],
)
def test_preview_geometry_and_mapper_rotation(pdf_env, rotation, cropbox, native_rect):
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    # 1. Generate real PDF with PyMuPDF
    pdf_path = str(tmp_path / "test.pdf")
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.set_rotation(rotation)
    if cropbox:
        page.set_cropbox(cropbox)
    doc.save(pdf_path)
    doc.close()

    # 2. Load PDF into ViewModel
    viewmodel.open_document(pdf_path)

    # 3. Create a region using native rect
    r = Rect(native_rect.x0, native_rect.y0, native_rect.x1, native_rect.y1)
    # the coordinate mapper inside viewmodel wants a rendered rect that maps back.
    # since we have a real pdf, we can get the mapper and inverse-map it so commit_selection gets the right input.
    mapper = viewmodel.get_mapper()
    rendered_rect = mapper.pdf_rect_to_rendered(r)
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()

    region = repo.get_all("p1")[0]
    region.status = RegionStatus.TRANSLATED
    region.translated_text = "Rotated Preview"
    repo.save(region)

    viewmodel.toggle_preview(True)

    # 4. Assert geometry
    assert len(widget._preview_items) == 1
    preview_item = widget._preview_items[0]

    mapper = viewmodel.get_mapper()
    expected_rendered = mapper.pdf_rect_to_rendered(r)
    expected_qrect = QRectF(
        expected_rendered.x0,
        expected_rendered.y0,
        expected_rendered.width,
        expected_rendered.height,
    )

    # Allow tiny float precision differences
    assert abs(preview_item.rect().x() - expected_qrect.x()) < 1e-4
    assert abs(preview_item.rect().y() - expected_qrect.y()) < 1e-4
    assert abs(preview_item.rect().width() - expected_qrect.width()) < 1e-4
    assert abs(preview_item.rect().height() - expected_qrect.height()) < 1e-4


def test_preview_lifecycle_full(pdf_env):
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    # 1. Generate PDF (2 pages)
    pdf_path = str(tmp_path / "lifecycle.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=400)
    doc.new_page(width=400, height=400)
    doc.save(pdf_path)
    doc.close()

    viewmodel.open_document(pdf_path)
    viewmodel.toggle_preview(True)

    assert len(widget._preview_items) == 0

    # Translate Again & Creation
    mapper = viewmodel.get_mapper()
    rendered_rect = mapper.pdf_rect_to_rendered(Rect(0, 0, 100, 100))
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()
    region = repo.get_all("p1")[0]

    # Translating using synchronous command execution
    from src.application.commands import TranslateRegionCommand
    from src.application.services.prompt_builder import TranslationPromptBuilder
    from src.application.services.token_protector import TokenProtector
    from src.application.use_cases.translate_region import (
        TranslateRegionRequest,
        TranslateRegionUseCase,
    )

    use_case = TranslateRegionUseCase(
        engine=viewmodel._translation_engine,
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder(),
    )
    req = TranslateRegionRequest(region.id, "English", "Spanish", False)
    old_snap, new_snap = use_case.execute(req)
    cmd = TranslateRegionCommand(old_snap, new_snap, repo)
    viewmodel._command_history.execute(cmd)

    # Manual refresh needed because we bypassed viewmodel signal propagation from task
    viewmodel._refresh_saved_regions()

    assert len(widget._preview_items) == 1
    original_text = widget._preview_items[0]._fallback_text
    assert "[TRANSLATED]" in original_text

    # Move/Resize via UI event
    viewmodel.move_resize_region(region.id, QRectF(50, 50, 100, 100))
    # Still translated, but rect changed
    assert len(widget._preview_items) == 1

    def assert_qrect_almost_equal(r1, r2):
        assert abs(r1.x() - r2.x()) < 1e-4
        assert abs(r1.y() - r2.y()) < 1e-4
        assert abs(r1.width() - r2.width()) < 1e-4
        assert abs(r1.height() - r2.height()) < 1e-4

    assert_qrect_almost_equal(widget._preview_items[0].rect(), QRectF(50, 50, 100, 100))
    assert widget._preview_items[0]._fallback_text == original_text

    # Undo
    viewmodel.undo()
    assert len(widget._preview_items) == 1
    assert_qrect_almost_equal(
        widget._preview_items[0].rect(),
        QRectF(rendered_rect.x0, rendered_rect.y0, rendered_rect.width, rendered_rect.height),
    )

    # Redo
    viewmodel.redo()
    assert_qrect_almost_equal(widget._preview_items[0].rect(), QRectF(50, 50, 100, 100))

    # Page Navigation
    viewmodel.next_page()
    assert viewmodel.current_page == 2
    assert len(widget._preview_items) == 0

    viewmodel.previous_page()
    assert viewmodel.current_page == 1
    assert len(widget._preview_items) == 1


def test_preview_transform_alignment(pdf_env):
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    pdf_path = str(tmp_path / "transform.pdf")
    doc = fitz.open()
    doc.new_page(width=800, height=1000)
    doc.save(pdf_path)
    doc.close()

    viewmodel.open_document(pdf_path)
    mapper = viewmodel.get_mapper()
    rendered_rect = mapper.pdf_rect_to_rendered(Rect(100, 100, 200, 200))
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()

    region = repo.get_all("p1")[0]
    region.status = RegionStatus.TRANSLATED
    region.translated_text = "Align"
    repo.save(region)
    viewmodel.toggle_preview(True)

    preview = widget._preview_items[0]
    saved = widget._saved_region_items[0]

    # Verify geometric alignment during different zooms
    # We map their rects to viewport to ensure they always stay perfectly aligned
    def assert_alignment():
        p_poly = widget.mapFromScene(preview.sceneTransform().mapRect(preview.rect()))
        s_poly = widget.mapFromScene(saved.sceneTransform().mapRect(saved.rect()))
        assert p_poly == s_poly

    # Zoom In
    viewmodel.zoom_in()
    assert_alignment()

    # Zoom Out
    viewmodel.zoom_out()
    assert_alignment()

    # Fit Width (forces a resize internally if size isn't right, but we test the zoom factor change)
    widget.resize(400, 400)
    viewmodel.set_zoom_mode(ZoomMode.FIT_WIDTH)
    assert_alignment()

    # Fit Page
    viewmodel.set_zoom_mode(ZoomMode.FIT_PAGE)
    assert_alignment()


def test_preview_dirty_draft_via_source_panel(pdf_env, qapp_instance):
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    # We need a MainWindow setup or SourcePanel setup to test real draft
    from src.ui.views.main_window import MainWindow

    main_window = MainWindow(viewmodel)
    main_window.pdf_widget = widget  # inject our widget
    source_panel = main_window.source_panel

    pdf_path = str(tmp_path / "draft.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=400)
    doc.save(pdf_path)
    doc.close()

    viewmodel.open_document(pdf_path)
    mapper = viewmodel.get_mapper()
    rendered_rect = mapper.pdf_rect_to_rendered(Rect(0, 0, 100, 100))
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()

    region = repo.get_all("p1")[0]
    region.status = RegionStatus.TRANSLATED
    region.translated_text = "Persisted Text"
    repo.save(region)
    viewmodel.toggle_preview(True)

    # Start Edit
    viewmodel._refresh_saved_regions()
    viewmodel.select_region(region.id)

    # Actually enter edit mode via source_panel
    source_panel._on_edit_clicked()

    # Simulate user typing into text_edit
    source_panel.translated_text_edit.setPlainText("Dirty Draft Typing...")

    # Dirty draft is now active. Preview should STILL say "Persisted Text"
    assert widget._preview_items[0]._fallback_text == "Persisted Text"

    # Apply draft
    source_panel.apply_draft()

    # Process events so the signal propagates
    qapp_instance.processEvents()

    # Now it should be updated
    assert widget._preview_items[0]._fallback_text == "Dirty Draft Typing..."


def test_preview_fast_move_preserves_translation(pdf_env):
    """
    Test that moving a region preserves translation if the extracted text is exactly the same.
    Also tests Undo/Redo over these moves.
    """
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    # 1. Generate PDF
    pdf_path = str(tmp_path / "fast_move.pdf")
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    # Put text clearly inside a box
    page.insert_text(fitz.Point(100, 100), "Stable Text")
    doc.save(pdf_path)
    doc.close()

    viewmodel.open_document(pdf_path)
    viewmodel.toggle_preview(True)
    mapper = viewmodel.get_mapper()

    # Use real extraction service instead of mock
    # Use real extraction service instead of mock
    from src.application.services.text_extraction import TextExtractionService
    from src.infrastructure.pdf.adapter import PyMuPDFDocument

    adapter = PyMuPDFDocument()
    adapter.open(pdf_path)
    viewmodel._extraction_service = TextExtractionService(adapter.get_text_extractor())

    # 2. Select and translate
    rendered_rect = mapper.pdf_rect_to_rendered(Rect(80, 80, 200, 120))
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()
    region = repo.get_all("p1")[0]

    region.status = RegionStatus.TRANSLATED
    region.translated_text = "Texto Estable"
    repo.save(region)
    viewmodel._refresh_saved_regions()

    # 3. Simulate fast moves (small offsets that don't change the extracted text)
    # We move it by 1 pixel several times
    for i in range(1, 4):
        offset_rect = QRectF(
            rendered_rect.x0 + i, rendered_rect.y0 + i, rendered_rect.width, rendered_rect.height
        )
        viewmodel.move_resize_region(region.id, offset_rect)

        # Verify it remains TRANSLATED
        updated_region = repo.get(region.id)
        assert updated_region.status == RegionStatus.TRANSLATED
        assert updated_region.translated_text == "Texto Estable"
        assert updated_region.source_text == "Stable Text"

    assert len(widget._preview_items) == 1
    assert widget._preview_items[0]._fallback_text == "Texto Estable"

    # 4. Undo and verify
    viewmodel.undo()
    updated_region = repo.get(region.id)
    assert updated_region.status == RegionStatus.TRANSLATED
    assert updated_region.translated_text == "Texto Estable"


def test_move_invalidates_translation(pdf_env):
    """
    Test that moving a region to a place where extraction yields different text invalidates it.
    """
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    # 1. Generate PDF
    pdf_path = str(tmp_path / "move_invalidation.pdf")
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text(fitz.Point(100, 100), "First Text")
    page.insert_text(fitz.Point(100, 200), "Second Text")
    doc.save(pdf_path)
    doc.close()

    viewmodel.open_document(pdf_path)
    viewmodel.toggle_preview(True)
    mapper = viewmodel.get_mapper()

    # Use real extraction service instead of mock
    from src.application.services.text_extraction import TextExtractionService
    from src.infrastructure.pdf.adapter import PyMuPDFDocument

    adapter = PyMuPDFDocument()
    adapter.open(pdf_path)
    viewmodel._extraction_service = TextExtractionService(adapter.get_text_extractor())

    # 2. Select First Text
    rendered_rect = mapper.pdf_rect_to_rendered(Rect(80, 80, 200, 120))
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()
    region = repo.get_all("p1")[0]

    region.status = RegionStatus.TRANSLATED
    region.translated_text = "Primer Texto"
    repo.save(region)
    viewmodel._refresh_saved_regions()

    # 3. Move to Second Text
    new_rect = mapper.pdf_rect_to_rendered(Rect(80, 180, 200, 220))
    viewmodel.move_resize_region(
        region.id, QRectF(new_rect.x0, new_rect.y0, new_rect.width, new_rect.height)
    )

    # 4. Verify invalidation
    updated_region = repo.get(region.id)
    assert updated_region.source_text != "First Text"
    assert updated_region.status == RegionStatus.PENDING
    assert not updated_region.translated_text

    # Preview should be gone since it's not TRANSLATED anymore
    assert len(widget._preview_items) == 0


def test_preview_fit_real():
    """
    Test que verifica el comportamiento cuando TextLayoutResult es FIT.
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QTextOption

    from src.domain.models.enums import FitStatus
    from src.domain.value_objects.render_plan import RegionRenderPlan, TextBlockPlan
    from src.domain.value_objects.geometry import Rect
    from src.ui.components.translation_preview_item import TranslationPreviewItem

    block1 = TextBlockPlan(rect=Rect(0,0,100,20), text="Linea 1", font_size=12.0, font_family="Arial")
    block2 = TextBlockPlan(rect=Rect(0,20,100,40), text="Linea 2", font_size=12.0, font_family="Arial")
    layout = RegionRenderPlan(
        region_id="r1",
        page_number=1,
        target_rect=Rect(0,0,100,100),
        blocks=(block1, block2),
        background_rgb=(255,255,255),
        fit_status=FitStatus.FIT
    )

    item = TranslationPreviewItem("r1", QRectF(0, 0, 100, 100), layout, "Fallback")

    assert tuple(b.text for b in item._layout.blocks) == ("Linea 1", "Linea 2")
    assert item._text_option.wrapMode() == QTextOption.NoWrap
    assert item._fallback_text == "Fallback"


def test_preview_raster_rendered_for_fit(monkeypatch):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    from src.domain.models.enums import FitStatus
    from src.domain.value_objects.layout import RenderedTextPreview
    from src.domain.value_objects.render_plan import RegionRenderPlan
    from src.domain.value_objects.geometry import Rect
    from src.ui.components.translation_preview_item import TranslationPreviewItem

    layout = RegionRenderPlan(
        region_id="r1",
        page_number=1,
        target_rect=Rect(0,0,100,100),
        blocks=(),
        background_rgb=(255,255,255),
        fit_status=FitStatus.FIT
    )

    raster = RenderedTextPreview(
        samples=b"\xff" * 100 * 100 * 3,
        width=100,
        height=100,
        stride=300,
        channels=3,
        render_scale=2.0,
    )

    base_rect = QRectF(10, 10, 100, 100)
    item = TranslationPreviewItem("r1", base_rect, layout, "Fallback", raster)

    image_calls = []

    def mock_drawImage(self, rect, image, *args, **kwargs):
        image_calls.append((rect, image))

    monkeypatch.setattr(QPainter, "drawImage", mock_drawImage)

    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)

    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    option = QStyleOptionGraphicsItem()

    try:
        item.paint(painter, option, None)
    finally:
        painter.end()

    assert len(image_calls) == 1
    call_rect, call_image = image_calls[0]

    assert call_rect == base_rect
    assert call_image.width() == 100
    assert call_image.height() == 100
    assert call_image.format() == QImage.Format_RGB888


def test_preview_overflow_real():
    """
    Test que verifica el comportamiento cuando TextLayoutResult es OVERFLOW.
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QTextOption

    from src.domain.models.enums import FitStatus
    from src.domain.value_objects.render_plan import RegionRenderPlan
    from src.domain.value_objects.geometry import Rect
    from src.ui.components.translation_preview_item import TranslationPreviewItem

    layout = RegionRenderPlan(
        region_id="r1",
        page_number=1,
        target_rect=Rect(0,0,100,100),
        blocks=(),
        background_rgb=(255,255,255),
        fit_status=FitStatus.OVERFLOW
    )

    item = TranslationPreviewItem("r1", QRectF(0, 0, 100, 100), layout, "Texto original largusimo")

    assert item._layout.blocks == ()
    assert item._text_option.wrapMode() == QTextOption.WordWrap
    assert item._fallback_text == "Texto original largusimo"


def test_preview_integration_callback(pdf_env):
    """
    Test de integración que verifica que el callback get_text_preview_func
    esté correctamente inyectado y es invocado al crear el preview item.
    """
    tmp_path, _db, repo, viewmodel, widget = pdf_env

    # We mock get_text_preview to ensure it's called
    preview_called = False
    original_get_preview = viewmodel.get_text_preview

    def mock_get_preview(region_id):
        nonlocal preview_called
        preview_called = True
        return original_get_preview(region_id)

    viewmodel.get_text_preview = mock_get_preview
    widget.get_text_preview_func = viewmodel.get_text_preview

    # 1. Generate PDF
    pdf_path = str(tmp_path / "callback_test.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=400)
    doc.save(pdf_path)
    doc.close()

    viewmodel.open_document(pdf_path)

    # 2. Select and translate
    mapper = viewmodel.get_mapper()
    rendered_rect = mapper.pdf_rect_to_rendered(Rect(80, 80, 200, 120))
    viewmodel.commit_selection(rendered_rect)
    viewmodel.save_region()
    region = repo.get_all("p1")[0]

    region.status = RegionStatus.TRANSLATED
    region.translated_text = "Texto Traducido"
    repo.save(region)

    # 3. Enable Preview -> triggers saved_regions_changed internally
    viewmodel.toggle_preview(True)

    assert preview_called is True
    assert len(widget._preview_items) == 1
    assert widget._preview_items[0]._fallback_text == "Texto Traducido"
