import pytest
import datetime
import sqlite3
import os
import hashlib
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


def test_prepare_pdf_export_with_real_sqlite(temp_db, dummy_pdf, tmp_path):
    # Use actual repositories
    from src.infrastructure.persistence.database import Database

    db = Database(temp_db)

    project_repo = SqliteProjectRepository(db)
    region_repo = SqliteTranslationRegionRepository(db)

    # 1. Create and save a Project
    with open(dummy_pdf, "rb") as f:
        content = f.read()

    sha256 = hashlib.sha256(content).hexdigest()
    size = len(content)

    project = Project(
        id="proj-123",
        name="Test Project",
        pdf_path=dummy_pdf,
        pdf_sha256=sha256,
        pdf_size=size,
        pdf_page_count=1,
        last_viewed_page=1,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
    )
    project_repo.save(project)

    # 2. Guardar varias TranslationRegion en SQLite
    region1 = TranslationRegion(
        id="reg-1", project_id="proj-123", page_id=1, selection_rect=Rect(0, 0, 100, 100)
    )
    region1.status = RegionStatus.TRANSLATED
    region1.translation_revision = 1
    region1.approved_translation_revision = 1
    region1.translated_text = "Hello world"
    region_repo.save(region1)

    region2 = TranslationRegion(
        id="reg-2", project_id="proj-123", page_id=1, selection_rect=Rect(150, 150, 200, 200)
    )
    region2.status = RegionStatus.TRANSLATED
    region2.translation_revision = 1
    region2.approved_translation_revision = 1
    region2.translated_text = "Testing 123"
    region_repo.save(region2)

    # Ensure get_all returns them
    saved_regions = region_repo.get_all("proj-123")
    assert len(saved_regions) == 2

    # 3. Ejecutar PreparePdfExportUseCase
    from src.infrastructure.pdf.source_inspector import PyMuPDFPdfSourceInspector
    from src.infrastructure.pdf.background_analyzer import PyMuPDFRegionBackgroundAnalyzer
    from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine

    use_case = PreparePdfExportUseCase(
        project_repo=project_repo,
        region_repo=region_repo,
        source_inspector=PyMuPDFPdfSourceInspector(),
        background_analyzer=PyMuPDFRegionBackgroundAnalyzer(),
        layout_engine=PyMuPDFTextLayoutEngine(),
    )

    dest_path = str(tmp_path / "dest.pdf")

    # 4 & 5. Verify it recovers regions successfully without AttributeError
    outcome = use_case.execute(
        "proj-123", dest_path, pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY
    )

    # It should succeed if layout and background are fine
    assert outcome.report.can_export is True
    assert outcome.report.exportable_regions == 2
    assert outcome.request is not None
    assert len(outcome.request.specs) == 2
    assert outcome.request.specs[0].translated_text in ["Hello world", "Testing 123"]
