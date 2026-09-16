import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable
from src.domain.interfaces.translation import ITranslationEngine
from src.application.dtos.translation_execution_config import TranslationExecutionConfig


class BatchJobStatus(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


@dataclass
class BatchJob:
    batch_job_id: str
    region_id: str
    status: BatchJobStatus
    error_message: str | None = None
    original_engine: str | None = None


class BatchSnapshot:
    """Freezes the configuration for the batch so it doesn't change mid-way."""
    def __init__(self, config: TranslationExecutionConfig):
        self.config = config


class TranslationBatchCoordinator:
    """
    Coordinates a batch of translations sequentially to avoid freezing the UI
    and saturating the local LLM.
    """
    def __init__(
        self, 
        dispatch_callback: Callable[[str, str, BatchSnapshot], None],
        on_progress_callback: Callable[[int, int], None] = None,
        on_finished_callback: Callable[[dict], None] = None,
        on_job_status_changed_callback: Callable[[str, BatchJobStatus], None] = None
    ):
        self._dispatch_callback = dispatch_callback
        self.on_progress_callback = on_progress_callback
        self.on_finished_callback = on_finished_callback
        self.on_job_status_changed_callback = on_job_status_changed_callback
        
        self.batch_id: str | None = None
        self.jobs: list[BatchJob] = []
        self.snapshot: BatchSnapshot | None = None
        
        # Concurrency
        self.max_concurrent_translations = 1
        self._active_count = 0
        self._active_job_ids = set()
        self._is_cancelled = False
        self._circuit_breaker_open = False
        self._pumping = False
        
    @property
    def is_active(self):
        return self.batch_id is not None and (self._active_count > 0 or self._has_queued_jobs()) and not self._is_cancelled

    @property
    def queued_region_ids(self) -> set[str]:
        if not self.batch_id:
            return set()
        return {j.region_id for j in self.jobs if j.status in (BatchJobStatus.QUEUED, BatchJobStatus.RUNNING)}

    def start_batch(self, region_ids: list[str], snapshot: BatchSnapshot):
        self.batch_id = str(uuid.uuid4())
        self.snapshot = snapshot
        self._is_cancelled = False
        self._circuit_breaker_open = False
        self._pumping = False
        self._active_job_ids.clear()
        self._active_count = 0
        
        self.jobs = [
            BatchJob(batch_job_id=str(uuid.uuid4()), region_id=r_id, status=BatchJobStatus.QUEUED)
            for r_id in region_ids
        ]
        
        self._emit_progress()
        self._pump_queue()

    def cancel_batch(self):
        self._is_cancelled = True
        for job in self.jobs:
            if job.status == BatchJobStatus.QUEUED:
                job.status = BatchJobStatus.CANCELLED
                if self.on_job_status_changed_callback:
                    self.on_job_status_changed_callback(job.region_id, job.status)
        self._check_finished()

    def report_job_started(self, region_id: str, batch_id: str):
        if batch_id != self.batch_id:
            return
        
        job = self._get_job(region_id)
        if job and job.status == BatchJobStatus.QUEUED:
            job.status = BatchJobStatus.RUNNING
            if self.on_job_status_changed_callback:
                self.on_job_status_changed_callback(region_id, job.status)

    def report_job_finished(self, region_id: str, batch_id: str, success: bool, error_code: str | None = None, error_msg: str | None = None):
        if batch_id != self.batch_id:
            return
            
        job = self._get_job(region_id)
        if not job:
            return

        if region_id in self._active_job_ids:
            self._active_job_ids.remove(region_id)
            self._active_count = max(0, self._active_count - 1)
        else:
            return # Already processed or never active

        if self._is_cancelled:
            job.status = BatchJobStatus.CANCELLED
        else:
            if success:
                job.status = BatchJobStatus.SUCCEEDED
            else:
                job.status = BatchJobStatus.FAILED
                job.error_message = error_msg
                if self._should_open_circuit_breaker(error_code, error_msg):
                    self._circuit_breaker_open = True
                    self._skip_remaining_jobs(f"Skipped due to engine failure: {error_msg}")

        if self.on_job_status_changed_callback:
            self.on_job_status_changed_callback(region_id, job.status)
        self._emit_progress()
        
        if not self._is_cancelled and not self._circuit_breaker_open:
            self._pump_queue()
        
        self._check_finished()

    def retry_failed(self):
        failed_jobs = [j.region_id for j in self.jobs if j.status in (BatchJobStatus.FAILED, BatchJobStatus.SKIPPED)]
        if not failed_jobs or not self.snapshot:
            return
        self.start_batch(failed_jobs, self.snapshot)

    def _pump_queue(self):
        if self._is_cancelled or self._circuit_breaker_open or self._pumping:
            return
            
        self._pumping = True
        try:
            while self._active_count < self.max_concurrent_translations:
                next_job = next((j for j in self.jobs if j.status == BatchJobStatus.QUEUED), None)
                if not next_job:
                    break
                    
                self._active_count += 1
                self._active_job_ids.add(next_job.region_id)
                self._dispatch_callback(next_job.region_id, self.batch_id, self.snapshot)
        finally:
            self._pumping = False

    def _get_job(self, region_id: str) -> BatchJob | None:
        return next((j for j in self.jobs if j.region_id == region_id), None)
        
    def _has_queued_jobs(self) -> bool:
        return any(j.status == BatchJobStatus.QUEUED for j in self.jobs)
        
    def _emit_progress(self):
        completed = sum(1 for j in self.jobs if j.status in (BatchJobStatus.SUCCEEDED, BatchJobStatus.FAILED, BatchJobStatus.CANCELLED, BatchJobStatus.SKIPPED))
        if self.on_progress_callback:
            self.on_progress_callback(completed, len(self.jobs))
        
    def _check_finished(self):
        if self._active_count == 0 and not self._has_queued_jobs():
            # Batch terminal
            summary = {
                "SUCCEEDED": sum(1 for j in self.jobs if j.status == BatchJobStatus.SUCCEEDED),
                "FAILED": sum(1 for j in self.jobs if j.status == BatchJobStatus.FAILED),
                "CANCELLED": sum(1 for j in self.jobs if j.status == BatchJobStatus.CANCELLED),
                "SKIPPED": sum(1 for j in self.jobs if j.status == BatchJobStatus.SKIPPED),
            }
            if self.on_finished_callback:
                self.on_finished_callback(summary)
            # Cleanup reference to avoid dangling references
            self.batch_id = None

    def _should_open_circuit_breaker(self, error_code: str | None, error_msg: str | None) -> bool:
        if error_code == "STRUCTURAL_MARKER_MISMATCH":
            return False
        
        if not error_msg:
            return False
        error_msg_lower = error_msg.lower()
        if "engine_unavailable" in error_msg_lower or "model_not_found" in error_msg_lower:
            return True
        if "connection" in error_msg_lower or "unavailable" in error_msg_lower or "not found" in error_msg_lower:
            # For resilience with existing strings
            return True
        return False
        
    def _skip_remaining_jobs(self, reason: str):
        for job in self.jobs:
            if job.status == BatchJobStatus.QUEUED:
                job.status = BatchJobStatus.SKIPPED
                job.error_message = reason
                if self.on_job_status_changed_callback:
                    self.on_job_status_changed_callback(job.region_id, job.status)
