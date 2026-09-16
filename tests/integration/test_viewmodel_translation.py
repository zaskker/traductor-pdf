from datetime import UTC
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThreadPool

from src.application.services.pdf_viewer_service import PdfViewerService
from src.application.services.project_service import ProjectService
from src.domain.models.enums import RegionStatus
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.infrastructure.translation.fake_engine import FakeTranslationEngine
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


class DummyRegionRepo:
    def __init__(self):
        self.regions = {}

    def save(self, region):
        self.regions[region.id] = region

    def get(self, rid):
        return self.regions.get(rid)

    def delete(self, rid):
        if rid in self.regions:
            del self.regions[rid]

    def get_by_page(self, pid, p):
        return list(self.regions.values())


@pytest.fixture
def repo():
    return DummyRegionRepo()


@pytest.fixture
def project_service(repo):
    ps = MagicMock()
    ps.region_repo = repo
    return ps


@pytest.fixture
def fake_engine():
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola"}
    return engine


@pytest.fixture
def viewmodel(project_service, fake_engine):
    service = MagicMock(spec=PdfViewerService)
    vm = PdfViewerViewModel(service, None, project_service, translation_engine=fake_engine)
    from datetime import datetime

    vm._current_project = Project(
        id="proj_1",
        name="test",
        pdf_path="f",
        pdf_sha256="123",
        pdf_size=10,
        pdf_page_count=1,
        last_viewed_page=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Mock QThreadPool to run synchronously in tests
    original_start = QThreadPool.globalInstance().start
    QThreadPool.globalInstance().start = lambda w: w.run()
    yield vm
    QThreadPool.globalInstance().start = original_start


@pytest.fixture
def region(repo):
    from datetime import datetime

    r = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        updated_at=datetime.now(UTC),
    )
    repo.save(r)
    return r


def test_translate_in_flight_blocked_double_click(viewmodel, region):
    # Temporarily remove the mock so we can test the guard BEFORE it finishes
    QThreadPool.globalInstance().start = lambda w: None  # Don't run it

    viewmodel.translate_region("reg_1")
    assert "reg_1" in viewmodel.in_flight_region_ids

    # second call should be ignored, active workers length remains 1
    viewmodel.translate_region("reg_1")
    assert len(viewmodel.active_workers) == 1


def test_translate_cleanup_after_success(viewmodel, region, repo):
    viewmodel.translate_region("reg_1")

    # In-flight should be cleared
    assert "reg_1" not in viewmodel.in_flight_region_ids
    assert len(viewmodel.active_workers) == 0

    # And translated
    assert repo.get("reg_1").translated_text == "Hola"
    assert repo.get("reg_1").status == RegionStatus.TRANSLATED


def test_translate_stale_source_changed(viewmodel, region, repo):
    # Direct test of _on_translation_finished with stale data
    class MockWorker:
        project_id = "proj_1"
        region_id = "reg_1"
        source_text = "Hello_old"
        updated_at = "old_date"
        session_id = viewmodel._session_id

    # Simulate finishing a worker that had stale data
    viewmodel._on_translation_finished(region, region, MockWorker())

    assert repo.get("reg_1").status == RegionStatus.PENDING  # unchanged


def test_translate_stale_region_deleted(viewmodel, region, repo):
    # Direct test of _on_translation_finished with deleted region
    class MockWorker:
        project_id = "proj_1"
        region_id = "reg_1"
        source_text = "Hello"
        updated_at = region.updated_at
        session_id = viewmodel._session_id

    repo.delete("reg_1")

    # Simulate finishing a worker but region was deleted
    viewmodel._on_translation_finished(region, region, MockWorker())
    assert repo.get("reg_1") is None


def test_translate_concurrent_A_and_B(viewmodel, repo):
    from datetime import datetime

    r1 = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        updated_at=datetime.now(UTC),
    )
    r2 = TranslationRegion(
        id="reg_2",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        updated_at=datetime.now(UTC),
    )
    repo.save(r1)
    repo.save(r2)

    viewmodel.translate_region("reg_1")
    viewmodel.translate_region("reg_2")

    assert repo.get("reg_1").status == RegionStatus.TRANSLATED
    assert repo.get("reg_2").status == RegionStatus.TRANSLATED
