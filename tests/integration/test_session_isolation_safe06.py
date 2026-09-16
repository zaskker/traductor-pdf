import pytest
from PySide6.QtCore import Qt

from src.application.commands import CommandExecutionError
from src.application.services.pdf_viewer_service import PdfViewerService
from src.application.services.project_service import ProjectService
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.models.enums import RegionStatus
from src.domain.value_objects.geometry import Rect
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.ui.viewmodels.translation_worker import TranslationWorker
from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.infrastructure.pdf.adapter import PyMuPDFDocument
from src.application.use_cases.translate_region import TranslateRegionRequest, TranslateRegionUseCase

class MockEngine:
    def __init__(self):
        self.last_translated = ""
    def translate(self, system_prompt: str, user_prompt: str):
        from src.domain.interfaces.translation import TranslationResult
        return TranslationResult(self.last_translated, "mock", "1.0")

class MockExtractionService:
    def extract_from_selection(self, selection):
        from src.domain.value_objects.extraction import TextExtractionResult, TextFragment
        from src.domain.value_objects.geometry import Rect
        return TextExtractionResult(selection.page_number, selection.pdf_rect, "Test Extract", [TextFragment("Test Extract", Rect(0,0,10,10), "Arial", 10, None)])

@pytest.fixture
def project_service(tmp_path):
    factory = SqlitePersistenceFactory()
    svc = ProjectService(factory)
    svc.base_dir = tmp_path
    return svc

@pytest.fixture
def viewmodel(project_service):
    adapter = PyMuPDFDocument()
    service = PdfViewerService(adapter)
    return PdfViewerViewModel(
        service=service,
        project_service=project_service,
        extraction_service=MockExtractionService(),
        translation_engine=MockEngine(),
    )

def create_dummy_pdf(path: str, content: str):
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), content)
    doc.save(path)
    doc.close()

def test_session_translation_isolation(viewmodel, project_service, tmp_path):
    pdf_A = tmp_path / "A.pdf"
    pdf_B = tmp_path / "B.pdf"
    create_dummy_pdf(str(pdf_A), "content_A")
    create_dummy_pdf(str(pdf_B), "content_B")
    
    # Mocks
    viewmodel._service.open_document = lambda path: None
    viewmodel._service.get_page_count = lambda: 1
    viewmodel._service.get_current_page_number = lambda: 1
    viewmodel._service.render_current_page = lambda s: None
    
    # 1. Open A
    viewmodel.open_document(str(pdf_A))
    session_A = viewmodel._session_id
    proj_A = viewmodel.current_project
    
    # 2. Start a translation in A
    # Create region directly
    region = TranslationRegion(
        id="region1", project_id=proj_A.id, page_id=1,
        source_text="Hello",
        selection_rect=Rect(0,0,100,100),
        status=RegionStatus.PENDING,
        source_fragments=[],
        translated_text=""
    )
    project_service.region_repo.save(region)
    
    viewmodel.translate_region("region1")
    assert "region1" in viewmodel.in_flight_region_ids
    assert len(viewmodel.active_workers) == 1
    worker_A = list(viewmodel.active_workers)[0]
    
    # 3. Open B
    viewmodel.open_document(str(pdf_B))
    session_B = viewmodel._session_id
    assert session_B != session_A
    proj_B = viewmodel.current_project
    
    # Worker A finishes (simulate callback from thread)
    import copy
    old_region = copy.deepcopy(region)
    new_region = copy.deepcopy(region)
    new_region.translated_text = "Hola"
    
    viewmodel._on_translation_finished(old_region, new_region, worker_A)
    
    # Verify isolation
    assert "region1" not in viewmodel.in_flight_region_ids # It was cleared
    assert len(viewmodel.active_workers) == 0
    # SQLite should NOT have updated the region because it was rejected
    project_service.bind_to_project_db(str(tmp_path / proj_A.id / "project.sqlite"))
    persisted = project_service.region_repo.get("region1")
    assert persisted.translated_text == ""

def test_session_undo_redo_isolation(viewmodel, project_service, tmp_path):
    pdf_A = tmp_path / "A.pdf"
    pdf_B = tmp_path / "B.pdf"
    create_dummy_pdf(str(pdf_A), "content_A")
    create_dummy_pdf(str(pdf_B), "content_B")
    
    viewmodel._service.open_document = lambda path: None
    viewmodel._service.get_page_count = lambda: 1
    viewmodel._service.get_current_page_number = lambda: 1
    viewmodel._service.render_current_page = lambda s: None
    
    # Open A
    viewmodel.open_document(str(pdf_A))
    
    # Create command for A
    from src.application.commands import CreateRegionCommand
    from src.domain.models.region import RegionStatus
    region_A = TranslationRegion(
        id="regA", project_id=viewmodel.current_project.id, page_id=1,
        source_text="A", selection_rect=Rect(0,0,10,10), status=RegionStatus.PENDING,
        translated_text=""
    )
    cmd_A = CreateRegionCommand(region_A, project_service.region_repo)
    viewmodel.execute_command(cmd_A)
    assert viewmodel.can_undo is True
    
    # Open B
    viewmodel.open_document(str(pdf_B))
    
    # History must be clear
    assert viewmodel.can_undo is False
    assert viewmodel.can_redo is False
    
    # Doing undo should do nothing (and not crash or affect A)
    viewmodel.undo()
    
    # Verify A is intact
    project_service.bind_to_project_db(str(tmp_path / viewmodel._current_project.id / "project.sqlite")) # B's DB
    assert project_service.region_repo.get("regA") is None # B doesn't have it
    
    # Edición normal dentro de B
    region_B = TranslationRegion(
        id="regB", project_id=viewmodel.current_project.id, page_id=1,
        source_text="B", selection_rect=Rect(0,0,10,10), status=RegionStatus.PENDING,
        translated_text=""
    )
    cmd_B = CreateRegionCommand(region_B, project_service.region_repo)
    viewmodel.execute_command(cmd_B)
    
    assert viewmodel.can_undo is True
    assert project_service.region_repo.get("regB") is not None
    
    viewmodel.undo()
    assert project_service.region_repo.get("regB") is None
    
    viewmodel.redo()
    assert project_service.region_repo.get("regB") is not None

