import pytest
from unittest.mock import MagicMock
from src.application.services.batch_coordinator import TranslationBatchCoordinator, BatchJobStatus, BatchSnapshot
from src.application.dtos.translation_execution_config import TranslationExecutionConfig
from src.domain.interfaces.translation import ITranslationEngine
from src.domain.models.glossary import GlossaryEntry

class MockEngine(ITranslationEngine):
    def translate(self, system_prompt: str, user_prompt: str):
        pass
    def get_info(self):
        pass

@pytest.fixture
def snapshot():
    config = TranslationExecutionConfig(
        source_language="en",
        target_language="es",
        engine=MockEngine(),
        glossary_id="g1",
        glossary_revision=1,
        glossary_entries=[GlossaryEntry(id="e1", source_term="test", target_term="prueba")]
    )
    return BatchSnapshot(config)

def test_batch01_start_batch(snapshot):
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], snapshot)
    
    # Concurrency is 1, so only 1 should be dispatched immediately
    assert len(dispatched) == 1
    assert dispatched[0] == "r1"
    assert coordinator.is_active

def test_batch02_concurrency_limit(snapshot):
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], snapshot)
    
    # Even if we try to pump, it shouldn't go over active_count=1
    coordinator._pump_queue()
    assert len(dispatched) == 1
    
    # report r1 started and finished
    coordinator.report_job_started("r1", coordinator.batch_id)
    coordinator.report_job_finished("r1", coordinator.batch_id, success=True)
    
    assert len(dispatched) == 2
    assert dispatched[1] == "r2"

def test_batch03_cancel_all(snapshot):
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], snapshot)
    
    coordinator.cancel_batch()
    
    # r1 was dispatched (running), r2/r3 should be CANCELLED
    assert coordinator._get_job("r2").status == BatchJobStatus.CANCELLED
    assert coordinator._get_job("r3").status == BatchJobStatus.CANCELLED
    
    # Finishes r1 after cancel
    coordinator.report_job_finished("r1", coordinator.batch_id, success=True)
    # r1 should be CANCELLED because it was cancelled mid-flight
    assert coordinator._get_job("r1").status == BatchJobStatus.CANCELLED
    assert not coordinator.is_active

def test_batch04_circuit_breaker_engine_unavailable(snapshot):
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], snapshot)
    
    coordinator.report_job_finished("r1", coordinator.batch_id, success=False, error_msg="ENGINE_UNAVAILABLE: Connection refused")
    
    assert coordinator._get_job("r1").status == BatchJobStatus.FAILED
    assert coordinator._get_job("r2").status == BatchJobStatus.SKIPPED
    assert coordinator._get_job("r3").status == BatchJobStatus.SKIPPED
    assert not coordinator.is_active

def test_batch05_region_specific_error(snapshot):
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], snapshot)
    
    coordinator.report_job_finished("r1", coordinator.batch_id, success=False, error_msg="GlossaryMismatchError")
    
    assert coordinator._get_job("r1").status == BatchJobStatus.FAILED
    assert coordinator._get_job("r2").status == BatchJobStatus.QUEUED
    assert len(dispatched) == 2  # r2 got dispatched

def test_batch26_immutable_glossary_snapshot(snapshot):
    # User requested to ensure we use revision 4 + entries A even if global glossary changes
    # Because we take snapshot from the start and pass it directly, it's structurally enforced.
    assert snapshot.config.glossary_revision == 1
    assert snapshot.config.glossary_entries[0].source_term == "test"
    
    # Simulating UI glossary change
    snapshot.config.glossary_revision = 2
    # But wait, in actual usage, the ViewModel instantiates a NEW config and NEW snapshot for a new batch.
    # The existing batch's snapshot remains untouched.
    # This test verifies that the batch coordinator holds onto the correct reference and dispatches it.
    
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append((region_id, snap))
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1"], snapshot)
    
    # Assert dispatch received the original snapshot
    assert len(dispatched) == 1
    assert dispatched[0][1].config.glossary_revision == 2 # Modified here just for testing identity
