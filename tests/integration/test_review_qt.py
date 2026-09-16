import pytest
from unittest.mock import Mock, MagicMock
from PySide6.QtCore import Qt
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.domain.models.region import TranslationRegion, RegionStatus, ReviewStatus
from src.domain.value_objects.geometry import Rect
from src.domain.interfaces.translation import StaleTranslationRevisionError

def create_region(id="r1", app_rev=None, rev_rev=None, rev=1, status=RegionStatus.TRANSLATED, text="OK"):
    r = TranslationRegion(id, "p1", 1, Rect(0,0,10,10), source_fragments=())
    r.status = status
    r.translation_revision = rev
    r.reviewed_translation_revision = rev_rev
    r.approved_translation_revision = app_rev
    r.translated_text = text
    return r

@pytest.fixture
def viewmodel():
    from src.application.services.pdf_viewer_service import PdfViewerService
    service_mock = MagicMock(spec=PdfViewerService)
    project_mock = MagicMock()
    translation_mock = MagicMock()
    
    vm = PdfViewerViewModel(service_mock, project_mock, translation_mock, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
    return vm

# REV24 UNREVIEWED -> REVIEWED -> APPROVED -> edit -> UNREVIEWED.

class DummyUoW:
    def __init__(self, region_repo):
        self.region_repository = region_repo
        self.translation_memory_repository = MagicMock()
    
    def __enter__(self): return self
    def __exit__(self, *args): pass


def test_rev24_qt_review_lifecycle(viewmodel, qtbot):
    r1 = create_region("r1")
    viewmodel._current_page = 1
    viewmodel._project_id = "p1"
    viewmodel._project_service.region_repo.get = lambda r: r1
    viewmodel._project_service.region_repo.get_by_page = lambda p, pg: [r1]
    
    viewmodel.error_occurred.connect(lambda e: print(f'ERROR: {e}'))
    viewmodel.saved_regions_changed.connect(lambda: print('EMITTED'))
    def mock_save(r):
        r1.__dict__.update(r.__dict__)
    viewmodel._project_service.region_repo.save = mock_save
    viewmodel._project_service.uow = DummyUoW(viewmodel._project_service.region_repo)
    
    
    viewmodel.mark_translation_reviewed("r1", 1)
    assert r1.review_status == ReviewStatus.REVIEWED
    
    
    viewmodel.approve_translation("r1", 1)
    assert r1.review_status == ReviewStatus.APPROVED
    
    # Edit logic resets the revision in actual system
    r1.translated_text = "Edited"
    r1.translation_revision = 2
    assert r1.review_status == ReviewStatus.UNREVIEWED

# REV25 dos regiones mantienen estados independientes.
def test_rev25_two_regions_independent(viewmodel):
    r1 = create_region("r1")
    r2 = create_region("r2")
    
    viewmodel._current_page = 1
    viewmodel._project_id = "p1"
    
    def mock_get(r_id):
        if r_id == "r1": return r1
        if r_id == "r2": return r2
    viewmodel._project_service.region_repo.get = mock_get
    viewmodel._project_service.region_repo.get_by_page = lambda p, pg: [r1, r2]
    
    viewmodel.error_occurred.connect(lambda e: print(f'ERROR: {e}'))
    viewmodel.saved_regions_changed.connect(lambda: print('EMITTED'))
    def mock_save(r):
        if r.id == "r1": r1.__dict__.update(r.__dict__)
        if r.id == "r2": r2.__dict__.update(r.__dict__)
    viewmodel._project_service.region_repo.save = mock_save
    viewmodel._project_service.uow = DummyUoW(viewmodel._project_service.region_repo)
    
    viewmodel.mark_translation_reviewed("r1", 1)
    viewmodel.approve_translation("r1", 1)
    
    assert r1.review_status == ReviewStatus.APPROVED
    assert r2.review_status == ReviewStatus.UNREVIEWED

# REV26 stale action emits error signal
def test_rev26_stale_ui_action_error(viewmodel, qtbot):
    r1 = create_region("r1", rev=2)
    viewmodel._current_page = 1
    viewmodel._project_id = "p1"
    viewmodel._project_service.region_repo.get = lambda r: r1
    viewmodel._project_service.region_repo.get_by_page = lambda p, pg: [r1]
    
    # UI thought it was at revision 1, but db is at 2
    viewmodel.approve_translation("r1", 1) # Will invoke ApproveTranslationUseCase but error because 1 != 2
    
    # We must mock use case throwing error
    class MockApproveUseCase:
        def execute(self, r_id, rev):
            raise StaleTranslationRevisionError(f"Stale {rev}")
            
    viewmodel._approve_translation_use_case = MockApproveUseCase()
    
    # Stale action emits error signal
    with qtbot.waitSignal(viewmodel.error_occurred) as blocker:
        viewmodel.approve_translation("r1", 1)
        
    assert "Refresh" in blocker.args[0]
