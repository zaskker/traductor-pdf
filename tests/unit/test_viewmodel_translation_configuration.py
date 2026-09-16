from unittest.mock import MagicMock, patch

from src.application.use_cases.translate_region import TranslateRegionRequest
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


def test_viewmodel_passes_custom_languages_to_request():
    pdf_service = MagicMock()
    extraction_service = MagicMock()
    project_service = MagicMock()

    # Setup mock region repo to return a valid region
    mock_repo = MagicMock()
    mock_region = MagicMock()
    mock_region.source_text = "Valid text"
    mock_repo.get.return_value = mock_region
    project_service.region_repo = mock_repo

    viewmodel = PdfViewerViewModel(
        service=pdf_service,
        extraction_service=extraction_service,
        project_service=project_service,
        translation_engine=MagicMock(),
        source_language="French",
        target_language="German",
    )

    # Bypass active project/lock checks for the test
    viewmodel._current_project = MagicMock()
    viewmodel._current_project.id = "proj_1"
    viewmodel._is_project_locked = False

    with patch("PySide6.QtCore.QThreadPool.globalInstance") as mock_thread_pool:
        mock_pool_instance = MagicMock()
        mock_thread_pool.return_value = mock_pool_instance

        viewmodel.translate_region("reg_1")

        # Verify the request passed to TranslationWorker
        assert mock_pool_instance.start.call_count == 1
        worker = mock_pool_instance.start.call_args[0][0]
        request: TranslateRegionRequest = worker.request

        assert request.source_language == "French"
        assert request.target_language == "German"


def test_viewmodel_uses_default_languages_english_spanish():
    viewmodel = PdfViewerViewModel(
        service=MagicMock(),
        extraction_service=MagicMock(),
        project_service=MagicMock(),
        translation_engine=MagicMock(),
    )
    assert viewmodel._source_language == "English"
    assert viewmodel._target_language == "Spanish"
