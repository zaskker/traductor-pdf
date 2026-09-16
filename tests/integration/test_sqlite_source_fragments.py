import pytest
import datetime
import hashlib
import sqlite3
import fitz

from src.infrastructure.persistence.repository import (
    SqliteProjectRepository,
    SqliteTranslationRegionRepository,
)
from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
from src.infrastructure.pdf.source_inspector import PyMuPDFPdfSourceInspector
from src.infrastructure.pdf.background_analyzer import PyMuPDFRegionBackgroundAnalyzer
from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion, Rect
from src.domain.models.enums import RegionStatus
from src.domain.value_objects.extraction import SourceFragment, FragmentGranularity
from src.application.dtos.export import PendingRegionPolicy


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    from src.infrastructure.persistence.database import Database

    db = Database(db_path)
    db.init_schema()
    return db_path


@pytest.fixture
def dummy_pdf(tmp_path):
    pdf_path = str(tmp_path / "dummy.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()
    return pdf_path


class FakeBackgroundAnalyzer(PyMuPDFRegionBackgroundAnalyzer):
    def __init__(self):
        super().__init__()
        self.received_requests = []

    def analyze_many(self, source_path, requests):
        self.received_requests.extend(requests)
        return super().analyze_many(source_path, requests)


def test_prepare_pdf_export_with_real_sqlite_and_source_fragments(temp_db, dummy_pdf, tmp_path):
    from src.infrastructure.persistence.database import Database

    db = Database(temp_db)
    project_repo = SqliteProjectRepository(db)
    region_repo = SqliteTranslationRegionRepository(db)

    with open(dummy_pdf, "rb") as f:
        content = f.read()

    sha256 = hashlib.sha256(content).hexdigest()
    size = len(content)

    project = Project(
        id="proj-fragments",
        name="Fragments Project",
        pdf_path=dummy_pdf,
        pdf_sha256=sha256,
        pdf_size=size,
        pdf_page_count=1,
        last_viewed_page=1,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
    )
    project_repo.save(project)

    # Crear SourceFragments
    frag1 = SourceFragment(
        text="Fragment 1",
        bbox=Rect(10, 10, 50, 20),
        granularity=FragmentGranularity.WORD,
        block_index=0,
        line_index=0,
        span_index=0,
        raw_font_name="Helvetica",
        font_size=12.0,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False,
    )
    frag2 = SourceFragment(
        text="Fragment 2",
        bbox=Rect(60, 10, 90, 20),
        granularity=FragmentGranularity.WORD,
        block_index=0,
        line_index=0,
        span_index=1,
        raw_font_name="Helvetica",
        font_size=12.0,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False,
    )

    region1 = TranslationRegion(
        id="reg-frag-1",
        project_id="proj-fragments",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_fragments=(frag1, frag2),
    )
    region1.status = RegionStatus.TRANSLATED
    region1.translation_revision = 1
    region1.approved_translation_revision = 1
    region1.translated_text = "Hello fragments"
    region_repo.save(region1)

    fake_bg_analyzer = FakeBackgroundAnalyzer()

    use_case = PreparePdfExportUseCase(
        project_repo=project_repo,
        region_repo=region_repo,
        source_inspector=PyMuPDFPdfSourceInspector(),
        background_analyzer=fake_bg_analyzer,
        layout_engine=PyMuPDFTextLayoutEngine(),
    )

    dest_path = str(tmp_path / "dest.pdf")
    outcome = use_case.execute(
        "proj-fragments", dest_path, pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY
    )

    assert outcome.report.can_export is True
    assert len(fake_bg_analyzer.received_requests) == 1
    bg_request = fake_bg_analyzer.received_requests[0]

    # Validar que excludes contiene los bbox reales de los fragmentos, reconstruido sin AttributeError
    assert len(bg_request.excluded_fragment_rects) == 2
    assert bg_request.excluded_fragment_rects[0] == frag1.bbox
    assert bg_request.excluded_fragment_rects[1] == frag2.bbox


def test_source_fragment_contract():
    frag = SourceFragment(
        text="test",
        bbox=Rect(0, 0, 10, 10),
        granularity=FragmentGranularity.WORD,
        block_index=0,
        line_index=0,
        span_index=0,
        raw_font_name="Helvetica",
        font_size=12.0,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False,
    )
    assert frag.bbox == Rect(0, 0, 10, 10)
    assert hasattr(frag, "bbox")
    assert not hasattr(frag, "pdf_rect")
