from datetime import UTC, datetime

from PySide6.QtCore import QRectF

from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import ExtractionMethod
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


class MockPdfService:
    def get_coordinate_mapper(self, scale):
        class MockMapper:
            def rendered_rect_to_pdf(self, rect: Rect) -> Rect:
                # Let's say scale is 1.0, so rendered == pdf
                return Rect(rect.x0, rect.y0, rect.x1, rect.y1)

        return MockMapper()


class MockExtractionService:
    def extract_from_selection(self, selection):
        from src.domain.value_objects.extraction import (
            FragmentGranularity,
            SourceFragment,
            TextExtractionResult,
        )

        frag = SourceFragment(
            text="Mocked Text",
            bbox=selection.pdf_rect,
            granularity=FragmentGranularity.WORD,
            block_index=0,
            line_index=0,
            span_index=0,
            raw_font_name="Arial",
            font_size=10.0,
            font_color="#000000",
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
            text="Mocked Text",
            fragments=(frag,),
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            warnings=(),
        )


def _init_project(db: Database):
    with db.get_connection() as conn:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p1", "Test", "path", "sha", 100, 10, 1, now, now),
        )


def test_viewmodel_move_resize_qrectf_conversion(tmp_path):
    db = Database(str(tmp_path / "test.sqlite"))
    db.init_schema()
    _init_project(db)

    repo = SqliteTranslationRegionRepository(db)
    project = Project("p1", "Test", "path", "sha", 100, 10, 1, datetime.now(UTC), datetime.now(UTC))

    old_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_bbox=Rect(0, 0, 10, 10),
        source_text="TEXT A",
        source_fragments=(),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.save(old_region)

    class MockProjectService:
        region_repo = repo

        def get_current_project(self):
            return project

        def is_locked(self, project_id):
            return False

    viewmodel = PdfViewerViewModel(MockPdfService(), MockExtractionService(), MockProjectService())
    viewmodel._current_project_id = "p1"
    viewmodel._current_project = project

    errors = []
    viewmodel.error_occurred.connect(errors.append)

    # Simulate move/resize from UI with non-zero coordinates
    qrectf = QRectF(100.0, 200.0, 50.0, 30.0)
    viewmodel.move_resize_region("r1", qrectf)

    if errors:
        raise RuntimeError(f"Errors occurred: {errors}")

    # Check repository
    updated_region = repo.get("r1")
    assert updated_region.selection_rect == Rect(100.0, 200.0, 150.0, 230.0)
    assert updated_region.source_text == "Mocked Text"
