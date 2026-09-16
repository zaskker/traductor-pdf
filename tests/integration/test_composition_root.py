import pytest
import sqlite3
import datetime
import hashlib
import fitz

from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.application.services.project_service import ProjectService
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion, Rect
from src.domain.models.enums import RegionStatus
from src.composition.export_factory import ExportFactory


@pytest.fixture
def temp_persistence_factory(tmp_path):
    db_path = str(tmp_path / "test.db")
    from src.infrastructure.persistence.database import Database

    db = Database(db_path)
    db.init_schema()

    # We patch the default DB path for the factory?
    # Or just subclass it for testing.
    class TempSqlitePersistenceFactory(SqlitePersistenceFactory):
        def _get_db_path(self):
            return db_path

    return TempSqlitePersistenceFactory()


@pytest.fixture
def dummy_pdf(tmp_path):
    pdf_path = str(tmp_path / "dummy.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_composition_root_smoke(temp_persistence_factory, dummy_pdf, tmp_path):
    # This mimics main.py composition
    project_service = ProjectService(temp_persistence_factory)

    # We need to save a real project and region first to test extraction
    project, db_path = project_service.discover_or_create_project(dummy_pdf, 1)
    project_service.bind_to_project_db(db_path)
    project_service.open_project(project.id)

    region_repo = project_service.get_region_repository()
    region1 = TranslationRegion(
        id="reg-comp-1", project_id=project.id, page_id=1, selection_rect=Rect(10, 10, 50, 50)
    )
    region1.status = RegionStatus.TRANSLATED
    region1.translation_revision = 1
    region1.approved_translation_revision = 1
    region1.translated_text = "Smoke Test"
    region_repo.save(region1)

    # main.py proxies
    class ProjectRepoProxy:
        def get(self, project_id):
            return project_service._project_repo.get(project_id)

    class RegionRepoProxy:
        def get_all(self, project_id):
            return project_service.get_region_repository().get_all(project_id)

    # Composition
    use_case = ExportFactory.create_prepare_export_use_case(ProjectRepoProxy(), RegionRepoProxy())

    dest_path = str(tmp_path / "comp_dest.pdf")

    # Execute should load the region through the RegionRepoProxy and succeed
    outcome = use_case.execute(project.id, dest_path)

    assert outcome.report.can_export is True
    assert outcome.report.exportable_regions == 1
    assert outcome.request.specs[0].translated_text == "Smoke Test"
