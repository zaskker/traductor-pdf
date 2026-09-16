from datetime import UTC, datetime

import pytest

from src.application.ports.pdf_coordinate_mapper import IPdfCoordinateMapper
from src.domain.models.enums import RegionStatus
from src.domain.models.project import Project
from src.domain.value_objects.extraction import (
    ExtractionMethod,
    FragmentGranularity,
    SourceFragment,
    TextExtractionResult,
)
from src.domain.value_objects.geometry import Point, Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


class FakeMapper(IPdfCoordinateMapper):
    def rendered_point_to_pdf(self, pt: Point) -> Point:
        return pt

    def pdf_point_to_rendered(self, pt: Point) -> Point:
        return pt

    def rendered_rect_to_pdf(self, rect: Rect) -> Rect:
        return rect

    def pdf_rect_to_rendered(self, rect: Rect) -> Rect:
        return rect


class MockExtractionService:
    def extract_from_selection(self, selection):
        frag = SourceFragment(
            text=f"Text for {selection.pdf_rect.x0}",
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
            text=f"Text for {selection.pdf_rect.x0}",
            fragments=(frag,),
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            warnings=(),
        )


class MockPdfService:
    def __init__(self):
        self.page = 1

    def get_current_page_number(self):
        return self.page

    def get_coordinate_mapper(self, scale):
        return FakeMapper()


class MockProjectService:
    def __init__(self, repo):
        self.region_repo = repo


@pytest.fixture
def viewmodel_setup(tmp_path):
    db = Database(str(tmp_path / "test.sqlite"))
    db.init_schema()

    with db.get_connection() as conn:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p1", "Test", "path", "sha", 100, 10, 1, now, now),
        )

    repo = SqliteTranslationRegionRepository(db)
    project = Project("p1", "Test", "path", "sha", 100, 10, 1, datetime.now(UTC), datetime.now(UTC))

    viewmodel = PdfViewerViewModel(
        service=MockPdfService(),
        extraction_service=MockExtractionService(),
        project_service=MockProjectService(repo),
    )
    viewmodel._current_project = project
    viewmodel._document_loaded = True
    viewmodel._current_page = 1
    return viewmodel, repo


def test_transition_basic(viewmodel_setup):
    vm, repo = viewmodel_setup

    # 1. Create and save A
    rect_A = Rect(0, 0, 10, 10)
    vm.commit_selection(rect_A)
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    regions = repo.get_all("p1")
    assert len(regions) == 1
    region_A = regions[0]

    # 2. Select A
    vm.select_region(region_A.id)
    assert vm._selected_region_id == region_A.id

    # 3. Create temporary selection B
    rect_B = Rect(20, 20, 30, 30)
    vm.commit_selection(rect_B)

    # Assert B is current selection, A is no longer selected
    assert vm._current_selection is not None
    assert vm._current_selection.pdf_rect == rect_B
    assert vm._selected_region_id is None

    # Verify A remains intact
    assert repo.get(region_A.id) is not None


def test_transition_save_second_region(viewmodel_setup):
    vm, repo = viewmodel_setup

    # Save A
    vm.commit_selection(Rect(0, 0, 10, 10))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    region_A = repo.get_all("p1")[0]

    # Select A, create B, save B
    vm.select_region(region_A.id)
    vm.commit_selection(Rect(20, 20, 30, 30))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()

    regions = repo.get_all("p1")
    assert len(regions) == 2
    assert regions[0].id != regions[1].id


def test_transition_multiple_consecutive(viewmodel_setup):
    vm, repo = viewmodel_setup

    # A
    vm.commit_selection(Rect(0, 0, 10, 10))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    region_A = repo.get_all("p1")[0]
    vm.select_region(region_A.id)

    # B
    vm.commit_selection(Rect(20, 20, 30, 30))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    region_B = next(r for r in repo.get_all("p1") if r.id != region_A.id)
    vm.select_region(region_B.id)

    # C
    vm.commit_selection(Rect(40, 40, 50, 50))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()

    assert len(repo.get_all("p1")) == 3


def test_transition_translated_region(viewmodel_setup):
    vm, repo = viewmodel_setup

    vm.commit_selection(Rect(0, 0, 10, 10))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    region_A = repo.get_all("p1")[0]

    # Manually translate A
    region_A.translated_text = "Translated A"
    region_A.status = RegionStatus.TRANSLATED
    repo.save(region_A)

    vm.select_region(region_A.id)
    vm.commit_selection(Rect(20, 20, 30, 30))

    # Verify A is intact
    reloaded_A = repo.get(region_A.id)
    assert reloaded_A.translated_text == "Translated A"
    assert vm._selected_region_id is None


def test_transition_manually_edited(viewmodel_setup):
    vm, repo = viewmodel_setup

    vm.commit_selection(Rect(0, 0, 10, 10))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    region_A = repo.get_all("p1")[0]

    region_A.is_manually_edited = True
    region_A.translated_text = "Edited A"
    repo.save(region_A)

    vm.select_region(region_A.id)
    vm.commit_selection(Rect(20, 20, 30, 30))

    # Verify A is intact
    reloaded_A = repo.get(region_A.id)
    assert reloaded_A.is_manually_edited is True
    assert vm._selected_region_id is None


def test_transition_dirty_draft(viewmodel_setup):
    vm, repo = viewmodel_setup

    vm.commit_selection(Rect(0, 0, 10, 10))
    vm._extraction_result = MockExtractionService().extract_from_selection(vm._current_selection)
    vm.save_region()
    region_A = repo.get_all("p1")[0]

    class DummySourcePanel:
        def __init__(self):
            self.allow = True

        def resolve_dirty_draft(self):
            return self.allow

    class DummyMainWindow:
        def __init__(self, vm, panel):
            self.viewmodel = vm
            self.source_panel = panel

        def _on_selection_committed_intercept(self, rect):
            if not self.source_panel.resolve_dirty_draft():
                return
            self.viewmodel.commit_selection(rect)

    panel = DummySourcePanel()
    main_win = DummyMainWindow(vm, panel)

    vm.select_region(region_A.id)

    # 1. Draft active, user cancels
    panel.allow = False
    main_win._on_selection_committed_intercept(Rect(20, 20, 30, 30))

    # Assert A is still selected
    assert vm._selected_region_id == region_A.id

    # 2. Draft active, user discards/applies
    panel.allow = True
    main_win._on_selection_committed_intercept(Rect(20, 20, 30, 30))

    # Assert A is no longer selected
    assert vm._selected_region_id is None
    assert vm._current_selection.pdf_rect == Rect(20, 20, 30, 30)
