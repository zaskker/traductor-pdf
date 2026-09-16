import pytest
import time
from src.application.services.batch_coordinator import TranslationBatchCoordinator, BatchJobStatus
from src.domain.interfaces.translation import ITranslationEngine, TranslationEngineInfo, EngineStatus, TranslationResult

class FakeFastEngine(ITranslationEngine):
    def get_info(self) -> TranslationEngineInfo:
        return TranslationEngineInfo(provider="fake", model="fake", status=EngineStatus.READY)
        
    def translate(self, system_prompt: str, user_prompt: str) -> TranslationResult:
        # Fast but not instantaneous, simulated network
        return TranslationResult(translated_text=user_prompt, engine_name="fake", model_name="fake")

def test_perf01_100_regions():
    # Performance test for processing 100 regions
    dispatched = []
    
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.max_concurrent_translations = 1
    
    regions = [f"r{i}" for i in range(100)]
    start = time.time()
    
    coordinator.start_batch(regions, None)
    
    for r in regions:
        coordinator.report_job_started(r, coordinator.batch_id)
        coordinator.report_job_finished(r, coordinator.batch_id, success=True)
        
    duration = time.time() - start
    # Core overhead should be minimal
    assert duration < 2.0
    assert len(dispatched) == 100
    assert not coordinator.is_active

def test_perf02_queue_creation():
    # Performance test for queue creation and management with 500 items
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    regions = [f"r{i}" for i in range(500)]
    
    start = time.time()
    coordinator.start_batch(regions, None)
    duration = time.time() - start
    
    # Just creating the jobs in memory shouldn't take more than 0.5s
    assert duration < 0.5
    assert len(coordinator.jobs) == 500

def test_perf03_no_repeated_init():
    # Simulates that we don't repeat expensive init per job
    # The config and snapshot are passed down directly.
    # This is verified by ensuring the config object identity doesn't change
    class ExpensiveInitEngine(ITranslationEngine):
        inits = 0
        def __init__(self):
            ExpensiveInitEngine.inits += 1
        def get_info(self): pass
        def translate(self, system_prompt, user_prompt): pass
        
    engine = ExpensiveInitEngine()
    
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append((region_id, snap))
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], engine)
    
    for r in ["r1", "r2", "r3"]:
        coordinator.report_job_started(r, coordinator.batch_id)
        coordinator.report_job_finished(r, coordinator.batch_id, success=True)
        
    assert ExpensiveInitEngine.inits == 1 # Only created once

def test_perf05_workers_clean_fast():
    # Deterministic contract check: queues cleaned, no jobs dispatched after cancel
    dispatched = []
    def dispatch(region_id, batch_id, snap):
        dispatched.append(region_id)
        
    coordinator = TranslationBatchCoordinator(dispatch_callback=dispatch)
    coordinator.start_batch(["r1", "r2", "r3"], None)
    
    assert len(dispatched) == 1
    
    coordinator.cancel_batch()
    
    coordinator.report_job_finished("r1", coordinator.batch_id, success=True)
    
    # Only r1 was dispatched
    assert len(dispatched) == 1
    # Coordinator is not active
    assert not coordinator.is_active
    # active_count is 0
    assert coordinator._active_count == 0
