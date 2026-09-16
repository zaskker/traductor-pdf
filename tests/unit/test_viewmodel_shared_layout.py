from unittest.mock import Mock

from src.application.services.layout_factory import TextLayoutRequestFactory
from src.application.services.pdf_viewer_service import PdfViewerService
from src.application.services.project_service import ProjectService
from src.domain.models.enums import RegionStatus
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


def test_viewmodel_uses_shared_layout_factory():
    # Arrange
    service = Mock(spec=PdfViewerService)
    project_service = Mock(spec=ProjectService)
    layout_engine = Mock()

    vm = PdfViewerViewModel(
        service=service, project_service=project_service, text_layout_engine=layout_engine
    )

    region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(100, 100, 500, 200),
        translated_text="Prueba de layout",
    )
    region.status = RegionStatus.TRANSLATED

    project_service.region_repo = Mock()
    project_service.region_repo.get.return_value = region
    vm._current_project = Project(
        id="p1",
        name="test",
        pdf_path="test.pdf",
        pdf_sha256="abc",
        pdf_size=100,
        pdf_page_count=1,
        last_viewed_page=0,
        created_at=None,
        updated_at=None,
    )

    # Act
    vm.get_text_layout("r1")

    # Assert
    # The layout_engine.layout_text should have been called with the exact output of TextLayoutRequestFactory
    expected_input = TextLayoutRequestFactory.create_input(region)
    layout_engine.layout_text.assert_called_once_with(expected_input)
