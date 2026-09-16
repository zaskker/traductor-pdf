import os
import uuid
from unittest.mock import patch, MagicMock
import pytest
import pymupdf as fitz
from PySide6.QtCore import Qt

from src.infrastructure.pdf.adapter import PyMuPDFDocument
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.application.dtos.export import ExportRequest
from src.infrastructure.process.export_controller import ExportProcessController, ExportProcessState

@pytest.fixture
def mock_viewmodel(qtbot):
    pdf_adapter = PyMuPDFDocument()
    mock_service = MagicMock()
    mock_extraction = MagicMock()
    mock_project = MagicMock()
    mock_engine = MagicMock()
    
    vm = PdfViewerViewModel(
        service=mock_service,
        extraction_service=mock_extraction,
        project_service=mock_project,
        translation_engine=mock_engine,
        text_layout_engine=MagicMock(),
        text_preview_renderer=MagicMock(),
        source_language="English",
        target_language="Spanish",
        preview_use_case=MagicMock()
    )
    return vm

def test_HARD03_encrypted_pdf(tmp_path):
    pdf_path = tmp_path / "encrypted.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Secret")
    doc.save(str(pdf_path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="123")
    doc.close()

    adapter = PyMuPDFDocument()
    with pytest.raises(ValueError, match="Este PDF está protegido con contraseña y no puede abrirse en esta versión"):
        adapter.open(str(pdf_path))

def test_HARD04_malformed_pdf(tmp_path):
    pdf_path = tmp_path / "malformed.pdf"
    pdf_path.write_bytes(b"Not a PDF file at all")
    
    adapter = PyMuPDFDocument()
    with pytest.raises(RuntimeError, match="Failed to open PDF"):
        adapter.open(str(pdf_path))

def test_HARD24_double_batch(mock_viewmodel):
    mock_viewmodel._current_project = MagicMock()
    mock_viewmodel._is_project_locked = False
    mock_viewmodel.batch_coordinator = MagicMock()
    mock_viewmodel.batch_coordinator.is_active = True
    
    # If is_active is True, start_batch should return early without doing anything
    mock_viewmodel.start_batch(["region_1"])
    mock_viewmodel.batch_coordinator.start_batch.assert_not_called()

def test_HARD08_export_crash_cleanup(tmp_path):
    controller = ExportProcessController()
    
    dest_path = tmp_path / "output.pdf"
    req = ExportRequest(
        source_path=str(tmp_path / "source.pdf"),
        destination_path=str(dest_path),
        expected_fingerprint=MagicMock(),
        specs=()
    )
    
    # Mock launcher to prevent actual QProcess start
    with patch.object(controller._launcher, 'get_command', return_value=("echo", ["crash"])):
        controller.start("job_123", req)
        
        assert controller._temp_destination_path is not None
        assert "tmp.pdf" in controller._temp_destination_path
        
        # Simulate temp file creation
        temp_file = tmp_path / os.path.basename(controller._temp_destination_path)
        temp_file.write_text("dummy temp content")
        
        # Simulate crash
        controller._force_crash_or_protocol_error("ERROR", "Crash")
        
        # Should be cleaned up
        assert not temp_file.exists()
