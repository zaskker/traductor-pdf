from datetime import UTC, datetime

from src.application.dtos.pdf_selection import PdfSelection
from src.domain.models.project import Project
from src.domain.value_objects.extraction import (
    ExtractionMethod,
    FragmentGranularity,
    SourceFragment,
    TextExtractionResult,
)
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


class MockExtractionService:
    def extract_from_selection(self, selection):
        frag = SourceFragment(
            text="Extracted",
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
            text="Extracted",
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
        return None


class MockProjectService:
    def __init__(self, repo):
        self.region_repo = repo


def test_viewmodel_save_region_refreshes_ui(tmp_path):
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

    regions_emitted = []
    viewmodel.saved_regions_changed.connect(lambda r: regions_emitted.append(r))

    # 1. Simulate selection
    viewmodel._current_selection = PdfSelection(pdf_rect=Rect(0, 0, 10, 10), page_number=1)
    viewmodel._extraction_result = MockExtractionService().extract_from_selection(
        viewmodel._current_selection
    )

    # 2. Save region
    viewmodel.save_region()

    # Verify repository has it
    assert repo.count("p1") == 1

    # Verify UI was refreshed (signal emitted)
    assert len(regions_emitted) > 0
    assert len(regions_emitted[-1]) == 1
    assert regions_emitted[-1][0].source_text == "Extracted"
