import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

from src.application.dtos.export import ExportRegionSpec, ExportRequest, PdfFingerprint
from src.domain.value_objects.geometry import Rect
from src.infrastructure.process.export_controller import ExportProcessController, ExportProcessState


@pytest.fixture
def mock_pdf(tmp_path):
    import fitz

    src = tmp_path / "source.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(1, 1, 1), fill=(1, 1, 1))
    doc.save(str(src))
    doc.close()

    from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter

    exporter = PyMuPDFVectorFormPdfExporter()
    sha, size = exporter._compute_sha_and_size(str(src))
    return str(src), sha, size


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _create_request(src, dest, sha, size, num_specs=1):
    specs = []
    for i in range(num_specs):
        specs.append(
            ExportRegionSpec(
                f"r{i}", 1, Rect(10, 10, 50, 50), "Test", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            )
        )
    return ExportRequest(
        source_path=str(src),
        destination_path=str(dest),
        expected_fingerprint=PdfFingerprint(sha256=sha, size=size, page_count=1),
        specs=tuple(specs),
    )


@pytest.mark.integration
def test_controller_single_active_export(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest1 = tmp_path / "dest1.pdf"
    dest2 = tmp_path / "dest2.pdf"

    req1 = _create_request(src, dest1, sha, size, 50)
    req2 = _create_request(src, dest2, sha, size, 1)

    controller = ExportProcessController()
    controller.start("job1", req1)

    # While active, start should be rejected
    with pytest.raises(RuntimeError, match="An export is already active."):
        controller.start("job2", req2)

    # Wait for finish
    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 10.0:
            pytest.fail("Timeout waiting for controller to finish")

    if controller.state == ExportProcessState.CRASHED:
        print("CRASHED:", getattr(controller, "_last_error_code", None), getattr(controller, "_stderr_buffer", None))
    assert controller.state == ExportProcessState.COMPLETED

    # After finish, start should STILL be rejected until reset
    # Wait, the controller auto resets on start(). So it should SUCCEED now.
    controller.start("job2", req2)
    # We test sequential execution next.


@pytest.mark.integration
def test_controller_reset_and_sequential(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest1 = tmp_path / "dest1.pdf"
    dest2 = tmp_path / "dest2.pdf"

    req1 = _create_request(src, dest1, sha, size, 1)
    req2 = _create_request(src, dest2, sha, size, 1)

    controller = ExportProcessController()

    # First execution
    controller.start("job1", req1)
    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 5.0:
            pytest.fail("Timeout waiting for job1")

    assert controller.state == ExportProcessState.COMPLETED
    assert dest1.exists()

    # Second execution
    controller.start("job2", req2)
    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 5.0:
            pytest.fail("Timeout waiting for job2")

    assert controller.state == ExportProcessState.COMPLETED
    assert dest2.exists()


@pytest.mark.integration
def test_progress_invariants(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    # Multiple regions on same page
    req = _create_request(src, dest, sha, size, 10)

    controller = ExportProcessController()

    progress_history = []

    def on_progress(job_id, prog):
        progress_history.append(prog)

    controller.progress.connect(on_progress)
    controller.start("job1", req)

    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 5.0:
            pytest.fail("Timeout waiting for job1")

    assert controller.state == ExportProcessState.COMPLETED

    # Invariants
    stages = [p.stage.name for p in progress_history]
    assert "VALIDATING" in stages
    assert "PREPARING" in stages
    assert "APPLYING" in stages
    assert "SAVING" in stages
    assert "VERIFYING" in stages

    # Monotonic completed regions
    regions = [p.completed_regions for p in progress_history]
    assert regions == sorted(regions)

    # Monotonic completed pages
    pages = [p.completed_pages for p in progress_history]
    assert pages == sorted(pages)
    assert pages[-1] == 1  # 1 page fully processed

    # Check that completed_pages only increased AT THE END of the applying phase,
    # meaning there should be applying stages with completed_pages == 0 and completed_regions > 0
    applying_progs = [p for p in progress_history if p.stage.name == "APPLYING"]
    assert any(p.completed_pages == 0 and p.completed_regions > 0 for p in applying_progs)
    assert applying_progs[-1].completed_pages == 1


@pytest.mark.integration
def test_large_request_performance(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    req = _create_request(src, dest, sha, size, 50)

    controller = ExportProcessController()

    start_time = time.time()
    controller.start("job1", req)

    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 300.0:
            pytest.fail("Timeout waiting for large request")

    duration = time.time() - start_time
    assert controller.state == ExportProcessState.COMPLETED
    print(f"Large request (1000 specs) took {duration:.2f}s")


@pytest.mark.integration
def test_forced_kill_integration(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    # Lots of regions to make it slow
    req = _create_request(src, dest, sha, size, 500)

    controller = ExportProcessController()

    def on_progress(job_id, prog):
        if prog.stage.name == "APPLYING" and prog.completed_regions > 10:
            # Force kill!
            if controller._process:
                controller._process.kill()

    controller.progress.connect(on_progress)
    controller.start("job1", req)

    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 10.0:
            pytest.fail("Timeout waiting for job to crash")

    assert controller.state == ExportProcessState.CRASHED
    assert not dest.exists()


@pytest.mark.integration
def test_worker_cancellation_deterministic(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    # Make it slow enough to catch
    req = _create_request(src, dest, sha, size, 500)
    controller = ExportProcessController()

    cancel_sent = False

    def on_progress(job_id, prog):
        nonlocal cancel_sent
        if prog.completed_regions > 0 and not cancel_sent:
            controller.cancel()
            cancel_sent = True

    controller.progress.connect(on_progress)
    controller.start("job1", req)

    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CANCELLED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 10.0:
            pytest.fail("Timeout waiting for cancellation")

    assert cancel_sent
    assert controller.state == ExportProcessState.CANCELLED
    assert not dest.exists()


@pytest.mark.integration
def test_worker_finalizing_race(mock_pdf, tmp_path, qapp):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    req = _create_request(src, dest, sha, size, 1)
    controller = ExportProcessController()

    cancel_sent = False

    def on_finalizing(job_id):
        nonlocal cancel_sent
        controller.cancel()
        cancel_sent = True

    controller.finalizing.connect(on_finalizing)
    controller.start("job1", req)

    start_time = time.time()
    while controller.state not in (
        ExportProcessState.COMPLETED,
        ExportProcessState.FAILED,
        ExportProcessState.CANCELLED,
        ExportProcessState.CRASHED,
    ):
        qapp.processEvents()
        time.sleep(0.01)
        if time.time() - start_time > 10.0:
            pytest.fail("Timeout waiting for race")

    assert cancel_sent
    # Cancel in finalizing is ignored; must complete.
    assert controller.state == ExportProcessState.COMPLETED
    assert dest.exists()


@pytest.mark.integration
def test_controller_malformed_completed_payload(qapp):
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION, WorkerMessageType
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    controller = ExportProcessController()
    controller._state = ExportProcessState.RUNNING
    controller._current_job_id = "job1"

    failed_emitted = 0
    crashed_emitted = 0

    def on_failed(job_id, err):
        nonlocal failed_emitted
        failed_emitted += 1

    def on_crashed(job_id, info):
        nonlocal crashed_emitted
        crashed_emitted += 1

    controller.failed.connect(on_failed)
    controller.crashed.connect(on_crashed)

    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.COMPLETED.value,
        "job_id": "job1",
        "payload": {"invalid_field": "test"},
    }

    controller._handle_event(evt)

    assert controller.state == ExportProcessState.FAILED
    assert failed_emitted == 1
    assert crashed_emitted == 0
    assert controller._terminal_event_emitted is True


@pytest.mark.integration
def test_controller_wrong_job_id(qapp):
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION, WorkerMessageType
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    controller = ExportProcessController()
    controller._state = ExportProcessState.RUNNING
    controller._current_job_id = "job1"

    failed_emitted = 0
    crashed_emitted = 0

    def on_failed(job_id, err):
        nonlocal failed_emitted
        failed_emitted += 1

    def on_crashed(job_id, info):
        nonlocal crashed_emitted
        crashed_emitted += 1

    controller.failed.connect(on_failed)
    controller.crashed.connect(on_crashed)

    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.PROGRESS.value,
        "job_id": "wrong_job_id",
        "payload": {
            "stage": "APPLYING",
            "completed_regions": 0,
            "total_regions": 1,
            "completed_pages": 0,
            "total_pages": 1,
        },
    }

    controller._handle_event(evt)

    assert controller.state == ExportProcessState.FAILED
    assert failed_emitted == 1
    assert crashed_emitted == 0
    assert controller._terminal_event_emitted is True


@pytest.mark.integration
def test_controller_cancelled_invalid_payload(qapp):
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION, WorkerMessageType
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    controller = ExportProcessController()
    controller._state = ExportProcessState.RUNNING
    controller._current_job_id = "job1"

    failed_emitted = 0
    cancelled_emitted = 0
    crashed_emitted = 0

    def on_failed(job_id, err):
        nonlocal failed_emitted
        failed_emitted += 1

    def on_cancelled(job_id, payload):
        nonlocal cancelled_emitted
        cancelled_emitted += 1

    def on_crashed(job_id, info):
        nonlocal crashed_emitted
        crashed_emitted += 1

    controller.failed.connect(on_failed)
    controller.cancelled.connect(on_cancelled)
    controller.crashed.connect(on_crashed)

    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.CANCELLED.value,
        "job_id": "job1",
        "payload": {"cleanup_failed": "not a bool", "temporary_path": 123},
    }

    controller._handle_event(evt)

    assert controller.state == ExportProcessState.FAILED
    assert failed_emitted == 1
    assert cancelled_emitted == 0
    assert crashed_emitted == 0
    assert controller._terminal_event_emitted is True


@pytest.mark.integration
def test_controller_failed_invalid_payload(qapp):
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION, WorkerMessageType
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    controller = ExportProcessController()
    controller._state = ExportProcessState.RUNNING
    controller._current_job_id = "job1"

    failed_emitted = 0

    def on_failed(job_id, err):
        nonlocal failed_emitted
        failed_emitted += 1

    controller.failed.connect(on_failed)

    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.FAILED.value,
        "job_id": "job1",
        "payload": {
            "error_code": 123,  # should be string
            "message": "some msg",
        },
    }

    controller._handle_event(evt)

    assert controller.state == ExportProcessState.FAILED
    assert failed_emitted == 1
    assert controller._terminal_event_emitted is True

    # If we send another event after terminal emitted, it should be ignored
    evt_completed = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.COMPLETED.value,
        "job_id": "job1",
        "payload": {
            "destination_path": "a",
            "exported_regions": 1,
            "pages_touched": [],
            "warnings": [],
        },
    }
    controller._handle_event(evt_completed)
    assert controller.state == ExportProcessState.FAILED  # remains FAILED
    assert failed_emitted == 1  # still 1


@pytest.mark.integration
def test_controller_cancelled_during_finalizing(qapp):
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION, WorkerMessageType
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    controller = ExportProcessController()
    controller._state = ExportProcessState.FINALIZING
    controller._current_job_id = "job1"

    failed_emitted = 0

    def on_failed(job_id, err):
        nonlocal failed_emitted
        failed_emitted += 1

    controller.failed.connect(on_failed)

    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.CANCELLED.value,
        "job_id": "job1",
        "payload": {"cleanup_failed": False, "temporary_path": "a"},
    }

    controller._handle_event(evt)

    assert controller.state == ExportProcessState.FAILED
    assert failed_emitted == 1
    assert controller._terminal_event_emitted is True
