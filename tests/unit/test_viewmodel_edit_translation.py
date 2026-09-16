from datetime import UTC, datetime

import pytest

from src.application.services.project_service import ProjectService
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


class MockFailingRepo:
    def __init__(self):
        self.regions = {}

    def get(self, region_id):
        return self.regions.get(region_id)

    def save(self, region):
        raise RuntimeError("Database error")


class MockRepo:
    def __init__(self):
        self.regions = {}

    def get(self, region_id):
        return self.regions.get(region_id)

    def save(self, region):
        self.regions[region.id] = region


@pytest.fixture
def viewmodel_success():
    from src.application.ports.pdf_document import IPdfDocument
    from src.application.services.pdf_viewer_service import PdfViewerService

    class FakePdfDocument(IPdfDocument):
        def open(self, path):
            pass

        def close(self):
            pass

        def get_page_count(self):
            return 1

        def render_page(self, index, scale):
            return None

        def get_coordinate_mapper(self, index, scale):
            return None

    service = PdfViewerService(FakePdfDocument())
    vm = PdfViewerViewModel(service)
    repo = MockRepo()

    # Initialize a mock project and service
    project = Project(
        id="proj_1",
        name="Test",
        pdf_path="test.pdf",
        pdf_sha256="abc",
        pdf_size=10,
        pdf_page_count=1,
        last_viewed_page=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    region = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        translated_text="Hola",
    )
    repo.save(region)

    service = ProjectService(None)
    service.region_repo = repo
    vm._project_service = service
    vm._current_project = project
    return vm, repo


@pytest.fixture
def viewmodel_failing():
    from src.application.ports.pdf_document import IPdfDocument
    from src.application.services.pdf_viewer_service import PdfViewerService

    class FakePdfDocument(IPdfDocument):
        def open(self, path):
            pass

        def close(self):
            pass

        def get_page_count(self):
            return 1

        def render_page(self, index, scale):
            return None

        def get_coordinate_mapper(self, index, scale):
            return None

    service = PdfViewerService(FakePdfDocument())
    vm = PdfViewerViewModel(service)
    repo = MockFailingRepo()

    project = Project(
        id="proj_1",
        name="Test",
        pdf_path="test.pdf",
        pdf_sha256="abc",
        pdf_size=10,
        pdf_page_count=1,
        last_viewed_page=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    region = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        translated_text="Hola",
    )
    repo.regions[region.id] = region  # Inject directly to avoid failing save

    service = ProjectService(None)
    service.region_repo = repo
    vm._project_service = service
    vm._current_project = project
    return vm, repo


def test_viewmodel_edit_translation_success(viewmodel_success):
    vm, repo = viewmodel_success
    result = vm.edit_translation("reg_1", "Hola editado")
    assert result is True

    region = repo.get("reg_1")
    assert region.translated_text == "Hola editado"
    assert region.is_manually_edited is True

    # Command was added
    assert vm._command_history.can_undo


def test_viewmodel_edit_translation_no_op(viewmodel_success):
    vm, repo = viewmodel_success
    result = vm.edit_translation("reg_1", "Hola")

    assert result is True
    region = repo.get("reg_1")
    assert region.translated_text == "Hola"
    assert region.is_manually_edited is False

    # No command was added
    assert not vm._command_history.can_undo


def test_viewmodel_edit_translation_failure(viewmodel_failing):
    vm, repo = viewmodel_failing

    errors = []
    vm.error_occurred.connect(errors.append)

    result = vm.edit_translation("reg_1", "Hola editado")
    assert result is False

    # Command history unchanged
    assert not vm._command_history.can_undo

    # Persisted translation unchanged (since save failed and command caught it)
    region = repo.get("reg_1")
    assert region.translated_text == "Hola"
    assert not region.is_manually_edited

    assert len(errors) == 1
    assert "Failed to edit translation" in errors[0]
