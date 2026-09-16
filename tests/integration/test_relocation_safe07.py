import os
import shutil
import pytest
from PySide6.QtCore import Qt

from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.application.services.project_service import ProjectService
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.application.services.pdf_viewer_service import PdfViewerService
from src.infrastructure.pdf.adapter import PyMuPDFDocument
from src.domain.models.region import TranslationRegion
from src.domain.models.enums import RegionStatus
from src.domain.value_objects.geometry import Rect
from src.application.commands import CreateRegionCommand


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
        translation_engine=None,
    )


def create_dummy_pdf(path: str, content: str):
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), content)
    doc.save(path)
    doc.close()

def test_relocation_same_file_moved(viewmodel, project_service, tmp_path):
    pdf_A = tmp_path / "original.pdf"
    create_dummy_pdf(str(pdf_A), "content")
    
    viewmodel._service.open_document = lambda path: None
    viewmodel._service.get_page_count = lambda: 1
    viewmodel._service.get_current_page_number = lambda: 1
    viewmodel._service.render_current_page = lambda s: None
    
    # 1. Open original PDF
    viewmodel.open_document(str(pdf_A))
    proj_1_id = viewmodel.current_project.id
    
    # Add a region to it
    region = TranslationRegion(
        id="reg1", project_id=proj_1_id, page_id=1,
        source_text="A", selection_rect=Rect(0,0,10,10), status=RegionStatus.PENDING,
        translated_text=""
    )
    cmd = CreateRegionCommand(region, project_service.region_repo)
    viewmodel.execute_command(cmd)
    
    # 2. Close it
    viewmodel.close_document()
    
    # 3. Move the file
    pdf_B = tmp_path / "moved_folder" / "new_name.pdf"
    pdf_B.parent.mkdir()
    shutil.move(str(pdf_A), str(pdf_B))
    
    # 4. Open the new path
    viewmodel.open_document(str(pdf_B))
    
    # Verify that it loaded the SAME project ID
    assert viewmodel.current_project.id == proj_1_id
    
    # Verify that the path was updated in the model
    assert viewmodel.current_project.pdf_path == str(pdf_B)
    
    # Verify that regions are preserved
    assert project_service.region_repo.get("reg1") is not None
    
    # Verify persistence of the new path
    project_service.bind_to_project_db(str(tmp_path / proj_1_id / "project.sqlite"))
    persisted_proj = project_service.open_project(proj_1_id)
    assert persisted_proj.pdf_path == str(pdf_B)


def test_relocation_different_file_same_name(viewmodel, project_service, tmp_path):
    pdf_A = tmp_path / "original.pdf"
    create_dummy_pdf(str(pdf_A), "content_A")
    
    viewmodel._service.open_document = lambda path: None
    viewmodel._service.get_page_count = lambda: 1
    
    # Open A
    viewmodel.open_document(str(pdf_A))
    proj_A_id = viewmodel.current_project.id
    viewmodel.close_document()
    
    # Create another file with the same name but different content
    folder_B = tmp_path / "other_folder"
    folder_B.mkdir()
    pdf_B = folder_B / "original.pdf"
    create_dummy_pdf(str(pdf_B), "content_DIFFERENT")
    
    # Open B
    viewmodel.open_document(str(pdf_B))
    
    # Should NOT use the same project ID
    assert viewmodel.current_project.id != proj_A_id
    assert viewmodel.current_project.pdf_path == str(pdf_B)
