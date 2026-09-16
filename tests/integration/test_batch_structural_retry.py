import pytest
from src.application.services.batch_coordinator import TranslationBatchCoordinator, BatchSnapshot, BatchJobStatus
from src.domain.interfaces.translation import StructuralMarkerMismatchError
from src.application.dtos.translation_execution_config import TranslationExecutionConfig
from src.infrastructure.translation.fake_engine import FakeTranslationEngine

def test_batch_struct01_terminal_state():
    dispatch_calls = []
    
    def dispatch(region_id, batch_id, snap):
        dispatch_calls.append(region_id)
        
    def finished(summary):
        finished.summary = summary
        
    coord = TranslationBatchCoordinator(dispatch_callback=dispatch, on_finished_callback=finished)
    
    config = TranslationExecutionConfig(source_language="en", target_language="es", engine=FakeTranslationEngine())
    snap = BatchSnapshot(config)
    
    coord.start_batch(["r1", "r2"], snap)
    
    # Simulate R1 started & succeeded
    coord.report_job_started("r1", coord.batch_id)
    coord.report_job_finished("r1", coord.batch_id, success=True)
    
    # R2 started & failed structurally
    coord.report_job_started("r2", coord.batch_id)
    coord.report_job_finished("r2", coord.batch_id, success=False, error_code="STRUCTURAL_MARKER_MISMATCH", error_msg="mismatch")
    
    assert coord.is_active == False
    assert finished.summary["SUCCEEDED"] == 1
    assert finished.summary["FAILED"] == 1
    assert not coord._circuit_breaker_open

def test_batch_struct02_continuity():
    dispatch_calls = []
    def dispatch(region_id, batch_id, snap):
        dispatch_calls.append(region_id)
        
    coord = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coord.start_batch(["r1", "r2", "r3"], BatchSnapshot(TranslationExecutionConfig(source_language="en", target_language="es", engine=FakeTranslationEngine())))
    
    # R1 fails structurally
    coord.report_job_started("r1", coord.batch_id)
    coord.report_job_finished("r1", coord.batch_id, success=False, error_code="STRUCTURAL_MARKER_MISMATCH", error_msg="mismatch")
    
    assert not coord._circuit_breaker_open
    
    # R2 starts
    assert "r2" in dispatch_calls
    coord.report_job_started("r2", coord.batch_id)
    coord.report_job_finished("r2", coord.batch_id, success=True)
    
    # R3 starts
    assert "r3" in dispatch_calls
    coord.report_job_started("r3", coord.batch_id)
    coord.report_job_finished("r3", coord.batch_id, success=True)
    
    assert coord.is_active == False

def test_batch_struct03_ui_state(qtbot):
    from src.ui.components.batch_translation_widget import BatchTranslationWidget
    
    widget = BatchTranslationWidget()
    qtbot.addWidget(widget)
    
    def on_finished(summary):
        widget.on_batch_finished(summary)
        
    coord = TranslationBatchCoordinator(dispatch_callback=lambda r,b,s: None, on_finished_callback=on_finished)
    coord.start_batch(["r1"], BatchSnapshot(TranslationExecutionConfig(source_language="en", target_language="es", engine=FakeTranslationEngine())))
    
    widget.set_active()
    assert widget.cancel_btn.isHidden() == False
    
    coord.report_job_started("r1", coord.batch_id)
    coord.report_job_finished("r1", coord.batch_id, success=False, error_code="STRUCTURAL_MARKER_MISMATCH", error_msg="fail")
    
    assert coord.is_active == False
    assert widget.cancel_btn.isHidden() == True
    assert widget.retry_btn.isHidden() == False
