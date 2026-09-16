import pytest
import pymupdf as fitz
from unittest.mock import MagicMock
from PySide6.QtWidgets import QMessageBox

from src.application.dtos.export import PendingRegionPolicy
from src.domain.models.enums import RegionStatus
from src.domain.value_objects.geometry import Rect
from src.domain.models.region import TranslationRegion
from src.presentation.coordinators.export_ui_coordinator import ExportUiCoordinator
from src.application.services.pdf_viewer_service import PdfViewerService
from src.application.services.project_service import ProjectService
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.infrastructure.pdf.adapter import PyMuPDFDocument

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
    controller = MagicMock()
    
    vm = PdfViewerViewModel(
        service=service,
        project_service=project_service,
        extraction_service=MockExtractionService(),
        translation_engine=MockEngine(),
    )
    
    from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
    from src.application.ports.pdf_source_inspector import IPdfSourceInspector
    from src.application.ports.region_background_analyzer import IRegionBackgroundAnalyzer
    from src.application.ports.text_layout_engine import ITextLayoutEngine
    
    class FakeInspector(IPdfSourceInspector):
        def inspect(self, path):
            from src.application.dtos.export import PdfSourceInspection, PdfFingerprint
            # En lugar de "fake", usamos el fingerprint real del servicio
            f = project_service._compute_fingerprint(path)
            return PdfSourceInspection(PdfFingerprint(f[0], f[1], 1), False, False, False)
            
    class FakeAnalyzer(IRegionBackgroundAnalyzer):
        def analyze_background(self, req):
            from src.application.dtos.export import BackgroundAnalysis, BackgroundClassification
            return BackgroundAnalysis(req.region_id, BackgroundClassification.UNIFORM_WHITE, (255, 255, 255))
        def analyze_many(self, source_path, requests):
            return [self.analyze_background(r) for r in requests]
            
    class FakeLayoutEngine(ITextLayoutEngine):
        def layout_text(self, inputs):
            from src.domain.value_objects.layout import TextLayoutResult
            from src.domain.models.enums import FitStatus
            
            if inputs.text == "TEXTO MUY LARGO QUE NO ENTRA EN ESTE ESPACIO PEQUEÑO":
                return TextLayoutResult(font_size=10, status=FitStatus.OVERFLOW, lines=())
                
            return TextLayoutResult(font_size=10, status=FitStatus.FIT, lines=())
    
    class ProxyProjectRepo:
        def get(self, pid):
            return project_service._project_repo.get(pid)
            
    class ProxyRegionRepo:
        def get_all(self, pid):
            return project_service.region_repo.get_all(pid)

    vm.prepare_export_use_case = PreparePdfExportUseCase(
        project_repo=ProxyProjectRepo(),
        region_repo=ProxyRegionRepo(),
        source_inspector=FakeInspector(),
        background_analyzer=FakeAnalyzer(),
        layout_engine=FakeLayoutEngine()
    )
    vm._export_controller = controller
    return vm

def create_dummy_pdf(path: str, content: str = "Test"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), content)
    doc.save(path)
    doc.close()

def setup_dummy_project(viewmodel, tmp_path, regions):
    pdf_path = tmp_path / "dummy.pdf"
    create_dummy_pdf(str(pdf_path))
    
    viewmodel._service.open_document = lambda p: None
    viewmodel._service.get_page_count = lambda: 1
    viewmodel._service.get_current_page_number = lambda: 1
    viewmodel._service.render_current_page = lambda s: None
    
    viewmodel.open_document(str(pdf_path))
    
    from src.application.commands import CreateRegionCommand
    repo = viewmodel._project_service.region_repo
    
    for i, r in enumerate(regions):
        region = TranslationRegion(
            id=f"reg_{i}",
            project_id=viewmodel.current_project.id,
            page_id=1,
            source_text="Test",
            selection_rect=r['rect'],
            source_fragments=(),
            status=r['status'],
            translated_text=r.get('translated_text', ""),
            translation_revision=1,
            approved_translation_revision=1,
        )
        repo.save(region)
        
    return str(pdf_path), viewmodel.current_project.id

@pytest.fixture
def fake_ui_coordinator(viewmodel, monkeypatch):
    coord = ExportUiCoordinator(
        parent=None,
        use_case=viewmodel.prepare_export_use_case,
        controller=viewmodel._export_controller,
        resolve_dirty_draft_cb=lambda: True,
        get_project_id_cb=lambda: viewmodel.current_project.id if viewmodel.current_project else None,
        get_source_pdf_cb=lambda: viewmodel.current_project.pdf_path if viewmodel.current_project else None,
    )
    coord.start_export_flow = MagicMock()
    return coord

def test_safe08_t1_1_exportable_1_pending(viewmodel, fake_ui_coordinator, tmp_path, monkeypatch):
    regions = [
        {"rect": Rect(0,0,10,10), "status": RegionStatus.TRANSLATED, "translated_text": "OK"},
        {"rect": Rect(20,20,30,30), "status": RegionStatus.PENDING, "translated_text": ""}
    ]
    pdf_path, proj_id = setup_dummy_project(viewmodel, tmp_path, regions)
    dest_path = str(tmp_path / "out.pdf")
    
    class FakeQMessageBox:
        StandardButton = QMessageBox.StandardButton
        Yes = QMessageBox.StandardButton.Yes
        Cancel = QMessageBox.StandardButton.Cancel
        @staticmethod
        def question(p, t, msg, btns, df):
            return QMessageBox.StandardButton.Yes
    import src.presentation.coordinators.export_ui_coordinator as coord_module
    monkeypatch.setattr(coord_module, "QMessageBox", FakeQMessageBox)
    
    started_request = None
    def fake_start(proj_id, d_path, request):
        nonlocal started_request
        started_request = request
    fake_ui_coordinator._start_worker = fake_start
    
    print("EXECUTING PREFLIGHT FOR T1")
    outcome = fake_ui_coordinator.use_case.execute(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    print("T1 OUTCOME ISSUES:", outcome.report.issues)
    
    fake_ui_coordinator._execute_preflight(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    
    assert started_request is not None
    assert len(started_request.specs) == 1
    assert started_request.specs[0].region_id == "reg_0"

def test_safe08_t2_cancel(viewmodel, fake_ui_coordinator, tmp_path, monkeypatch):
    regions = [
        {"rect": Rect(0,0,10,10), "status": RegionStatus.TRANSLATED, "translated_text": "OK"},
        {"rect": Rect(20,20,30,30), "status": RegionStatus.PENDING, "translated_text": ""}
    ]
    pdf_path, proj_id = setup_dummy_project(viewmodel, tmp_path, regions)
    dest_path = str(tmp_path / "out.pdf")
    
    class FakeQMessageBox:
        StandardButton = QMessageBox.StandardButton
        Yes = QMessageBox.StandardButton.Yes
        Cancel = QMessageBox.StandardButton.Cancel
        @staticmethod
        def question(p, t, msg, btns, df):
            return QMessageBox.StandardButton.Cancel
    import src.presentation.coordinators.export_ui_coordinator as coord_module
    monkeypatch.setattr(coord_module, "QMessageBox", FakeQMessageBox)
    
    started_request = None
    def fake_start(proj_id, d_path, request):
        nonlocal started_request
        started_request = request
    fake_ui_coordinator._start_worker = fake_start
    
    fake_ui_coordinator._execute_preflight(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    
    assert started_request is None

def test_safe08_t3_1_overflow_1_pending(viewmodel, fake_ui_coordinator, tmp_path, monkeypatch):
    regions = [
        {"rect": Rect(0,0,10,10), "status": RegionStatus.TRANSLATED, "translated_text": "TEXTO MUY LARGO QUE NO ENTRA EN ESTE ESPACIO PEQUEÑO"},
        {"rect": Rect(20,20,30,30), "status": RegionStatus.PENDING, "translated_text": ""}
    ]
    pdf_path, proj_id = setup_dummy_project(viewmodel, tmp_path, regions)
    dest_path = str(tmp_path / "out.pdf")
    
    called_warning = False
    def fake_warning(p, t, msg):
        nonlocal called_warning
        called_warning = True
    class FakeQMessageBox:
        @staticmethod
        def warning(p, t, msg):
            fake_warning(p, t, msg)
    import src.presentation.coordinators.export_ui_coordinator as coord_module
    monkeypatch.setattr(coord_module, "QMessageBox", FakeQMessageBox)
    
    started_request = None
    def fake_start(proj_id, d_path, request):
        nonlocal started_request
        started_request = request
    fake_ui_coordinator._start_worker = fake_start
    
    fake_ui_coordinator._execute_preflight(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    
    assert started_request is None
    assert called_warning is True

def test_safe08_t6_all_pending(viewmodel, fake_ui_coordinator, tmp_path, monkeypatch):
    regions = [
        {"rect": Rect(0,0,10,10), "status": RegionStatus.PENDING, "translated_text": ""}
    ]
    pdf_path, proj_id = setup_dummy_project(viewmodel, tmp_path, regions)
    dest_path = str(tmp_path / "out.pdf")
    
    called_warning = False
    def fake_warning(p, t, msg):
        nonlocal called_warning
        called_warning = True
    class FakeQMessageBox:
        @staticmethod
        def warning(p, t, msg):
            fake_warning(p, t, msg)
    import src.presentation.coordinators.export_ui_coordinator as coord_module
    monkeypatch.setattr(coord_module, "QMessageBox", FakeQMessageBox)
    
    started_request = None
    def fake_start(proj_id, d_path, request):
        nonlocal started_request
        started_request = request
    fake_ui_coordinator._start_worker = fake_start
    
    fake_ui_coordinator._execute_preflight(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    
    assert started_request is None
    assert called_warning is True

def test_safe08_t7_no_regions(viewmodel, fake_ui_coordinator, tmp_path, monkeypatch):
    pdf_path, proj_id = setup_dummy_project(viewmodel, tmp_path, [])
    dest_path = str(tmp_path / "out.pdf")
    
    called_warning = False
    def fake_warning(p, t, msg):
        nonlocal called_warning
        called_warning = True
    class FakeQMessageBox:
        @staticmethod
        def warning(p, t, msg):
            fake_warning(p, t, msg)
    import src.presentation.coordinators.export_ui_coordinator as coord_module
    monkeypatch.setattr(coord_module, "QMessageBox", FakeQMessageBox)
    
    started_request = None
    def fake_start(proj_id, d_path, request):
        nonlocal started_request
        started_request = request
    fake_ui_coordinator._start_worker = fake_start
    
    fake_ui_coordinator._execute_preflight(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    
    assert started_request is None
    assert called_warning is True

def test_safe08_t8_status_and_path_intact(viewmodel, fake_ui_coordinator, tmp_path, monkeypatch):
    regions = [
        {"rect": Rect(0,0,10,10), "status": RegionStatus.TRANSLATED, "translated_text": "OK"},
        {"rect": Rect(20,20,30,30), "status": RegionStatus.PENDING, "translated_text": ""}
    ]
    pdf_path, proj_id = setup_dummy_project(viewmodel, tmp_path, regions)
    dest_path = str(tmp_path / "out.pdf")
    
    class FakeQMessageBox:
        StandardButton = QMessageBox.StandardButton
        Yes = QMessageBox.StandardButton.Yes
        Cancel = QMessageBox.StandardButton.Cancel
        @staticmethod
        def question(p, t, msg, btns, df):
            return QMessageBox.StandardButton.Yes
    import src.presentation.coordinators.export_ui_coordinator as coord_module
    monkeypatch.setattr(coord_module, "QMessageBox", FakeQMessageBox)
    
    started_request = None
    def fake_start(proj_id, d_path, request):
        nonlocal started_request
        started_request = request
    fake_ui_coordinator._start_worker = fake_start
    
    fake_ui_coordinator._execute_preflight(proj_id, dest_path, PendingRegionPolicy.BLOCK)
    
    assert viewmodel.current_project.pdf_path == pdf_path
    
    all_regs = viewmodel._project_service.region_repo.get_all(proj_id)
    assert all_regs[1].status == RegionStatus.PENDING
