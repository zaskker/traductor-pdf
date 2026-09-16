import pytest
from src.application.dtos.export import ApprovalExportPolicy
from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
from src.domain.models.project import Project
from src.application.dtos.export import ApprovalExportPolicy, PendingRegionPolicy
from src.domain.models.region import TranslationRegion, RegionStatus
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.source_inspector import PdfSourceInspection, PdfFingerprint

class DummyProjectRepo:
    def __init__(self, p): self.p = p
    def get(self, p_id): return self.p
    def save(self, p): pass

class DummyRegionRepo:
    def __init__(self, r): self.r = r
    def get_all(self, p_id): return self.r

class DummySourceInspector:
    def __init__(self, insp): self.insp = insp
    def inspect(self, path): return self.insp

class DummyBackgroundAnalyzer:
    def __init__(self, bg): self.bg = bg
    def analyze_many(self, path, requests): return list(self.bg.values())
    
class DummyLayoutEngine:
    def __init__(self, layout): self.layout = layout
    def layout_text(self, input_data): return list(self.layout.values())[0]

def create_region(id, app_rev=None, rev_rev=None, rev=1, status=RegionStatus.TRANSLATED, text="OK"):
    r = TranslationRegion(id, "p1", 1, Rect(int(id[-1])*20, 0, int(id[-1])*20+10, 10), source_fragments=())
    r.status = status
    r.translation_revision = rev
    r.reviewed_translation_revision = rev_rev
    r.approved_translation_revision = app_rev
    r.translated_text = text
    return r

@pytest.fixture
def use_case_factory(tmp_path):
    def _create(regions):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")
        p = Project("p1", "test", str(pdf_file), "hash", 100, 1, 1, None, None)
        insp = PdfSourceInspection(PdfFingerprint("hash", 100, 1), False, False, False)
        
        from src.application.dtos.export import BackgroundAnalysis, BackgroundClassification
        bg = {r.id: BackgroundAnalysis(r.id, BackgroundClassification.UNIFORM_WHITE, (255,255,255)) for r in regions}
        
        from src.domain.models.enums import FitStatus
        from src.domain.value_objects.layout import TextLayoutResult
        layout = {r.id: TextLayoutResult(12.0, FitStatus.FIT, ()) for r in regions}
        
        return PreparePdfExportUseCase(
            DummyProjectRepo(p),
            DummyRegionRepo(regions),
            DummySourceInspector(insp),
            DummyBackgroundAnalyzer(bg),
            DummyLayoutEngine(layout)
        )
    return _create

# REV18 APPROVED_ONLY exporta solamente aprobadas.
def test_rev18_approved_only(use_case_factory):
    r1 = create_region("r1", app_rev=1, rev_rev=1, rev=1) # Approved
    r2 = create_region("r2", rev=1) # Unreviewed
    
    uc = use_case_factory([r1, r2])
    outcome = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, approval_policy=ApprovalExportPolicy.APPROVED_ONLY)
    
    assert outcome.report.can_export is True
    assert outcome.report.exportable_regions == 1
    assert any(iss.code.name == "UNAPPROVED_REGIONS" for iss in outcome.report.issues)

# REV19 ALL_VALID_TRANSLATED incluye aprobadas + no aprobadas válidas.
def test_rev19_all_valid_translated(use_case_factory):
    r1 = create_region("r1", app_rev=1, rev_rev=1, rev=1) # Approved
    r2 = create_region("r2", rev=1) # Unreviewed
    
    uc = use_case_factory([r1, r2])
    outcome = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, approval_policy=ApprovalExportPolicy.ALL_VALID_TRANSLATED)
    
    assert outcome.report.can_export is True
    assert len(outcome.request.specs) == 2

# REV20 APPROVED + OVERFLOW sigue sin exportarse.
def test_rev20_approved_plus_overflow_no_export(use_case_factory):
    r1 = create_region("r1", app_rev=1, rev_rev=1, rev=1) # Approved
    uc = use_case_factory([r1])
    
    # Mocking overflow
    from src.domain.value_objects.layout import TextLayoutResult; from src.domain.models.enums import FitStatus
    uc._layout_engine = DummyLayoutEngine({"r1": TextLayoutResult(12.0, FitStatus.OVERFLOW, ())})
    
    outcome = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, approval_policy=ApprovalExportPolicy.APPROVED_ONLY)
    
    assert outcome.report.can_export is False
    assert any(iss.code.name == "OVERFLOW" for iss in outcome.report.issues)

# REV21 integración SAFE-08 pending + approval.
def test_rev21_safe08_pending_plus_approval(use_case_factory):
    r1 = create_region("r1", app_rev=1, rev_rev=1, rev=1) # Approved
    r2 = create_region("r2", status=RegionStatus.PENDING) # Pending
    
    uc = use_case_factory([r1, r2])
    outcome = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.BLOCK, approval_policy=ApprovalExportPolicy.APPROVED_ONLY)
    
    assert outcome.report.can_export is False
    assert any(iss.code.name == "PENDING_REGIONS" for iss in outcome.report.issues)

# REV22 Cancelar diálogo no inicia worker.
# This test belongs in UI testing or coordinator testing. 
# We'll assert that the coordinator handles it in the qt test or mock it here.
def test_rev22_cancel_dialog_no_worker(monkeypatch, use_case_factory):
    from src.presentation.coordinators.export_ui_coordinator import ExportUiCoordinator
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtCore import QObject
    class FakeParent(QObject): pass
    coord = ExportUiCoordinator(FakeParent(), use_case_factory([]), None, lambda: True, lambda: "p1", lambda: "src.pdf")
    
    r1 = create_region("r1", rev=1) # Unreviewed
    uc = use_case_factory([r1])
    coord.use_case = uc
    
    class FakeQMessageBox:
        RejectRole = QMessageBox.RejectRole
        ActionRole = QMessageBox.ActionRole
        def __init__(self, parent): self.parent = parent
        def setWindowTitle(self, title): pass
        warning = classmethod(lambda cls, *args: None)
        def setText(self, text): pass
        def addButton(self, text, role): return text
        def exec(self): pass
        def clickedButton(self): return "Cancelar"
        
    monkeypatch.setattr("src.presentation.coordinators.export_ui_coordinator.QMessageBox", FakeQMessageBox)
    
    worker_started = False
    def mock_start(*args): nonlocal worker_started; worker_started = True
    coord._start_worker = mock_start
    
    coord._execute_preflight("p1", "dest.pdf", PendingRegionPolicy.EXPORT_TRANSLATED_ONLY)
    assert not worker_started

# REV23 ExportRequest contiene exactamente IDs autorizados.
def test_rev23_export_request_ids(use_case_factory):
    r1 = create_region("r1", app_rev=1, rev_rev=1, rev=1) # Approved
    r2 = create_region("r2", app_rev=1, rev_rev=1, rev=1) # Approved
    r3 = create_region("r3", rev=1) # Unreviewed
    
    uc = use_case_factory([r1, r2, r3])
    outcome = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, approval_policy=ApprovalExportPolicy.APPROVED_ONLY)
    
    assert outcome.report.can_export is True
    assert outcome.report.exportable_regions == 2
    
    # if ALL_VALID_TRANSLATED
    outcome2 = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, approval_policy=ApprovalExportPolicy.ALL_VALID_TRANSLATED)
    assert outcome2.report.can_export is True
    assert len(outcome2.request.specs) == 3
    assert {s.region_id for s in outcome2.request.specs} == {"r1", "r2", "r3"}
