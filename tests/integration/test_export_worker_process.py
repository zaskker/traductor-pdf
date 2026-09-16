import json
import subprocess
import sys
import threading

import pytest
from PySide6.QtCore import QCoreApplication

from src.application.dtos.export import ExportRegionSpec, ExportRequest, PdfFingerprint
from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter
from src.infrastructure.process.serialization import serialize_export_request


@pytest.fixture
def mock_pdf(tmp_path):
    import fitz

    src = tmp_path / "source.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(1, 1, 1), fill=(1, 1, 1))
    doc.save(str(src))
    doc.close()

    # calc sha and size
    exporter = PyMuPDFVectorFormPdfExporter()
    sha, size = exporter._compute_sha_and_size(str(src))
    return str(src), sha, size


@pytest.fixture
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def _get_worker_cmd():
    return [sys.executable, "-m", "src.workers.pdf_export_worker"]


@pytest.mark.integration
def test_worker_real_success_subprocess(mock_pdf, tmp_path):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    req = ExportRequest(
        source_path=str(src),
        destination_path=str(dest),
        expected_fingerprint=PdfFingerprint(sha256=sha, size=size, page_count=1),
        specs=(
            ExportRegionSpec(
                region_id="r1",
                page_number=1,
                pdf_rect=Rect(10, 10, 100, 100),
                translated_text="Success IPC",
                font_family="helv",
                font_size=12.0,
                background_rgb=(255, 255, 255), font_color=(0, 0, 0),
            ),
        ),
    )

    payload = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": "EXPORT_REQUEST",
        "job_id": "job123",
        "payload": json.loads(serialize_export_request(req)),
    }
    req_json = json.dumps(payload) + "\n"

    proc = subprocess.Popen(
        _get_worker_cmd(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Need to read READY first
    ready_line = proc.stdout.readline()
    assert "READY" in ready_line

    # Send request
    proc.stdin.write(req_json)
    proc.stdin.flush()

    events = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
            events.append(evt)
        except Exception:
            pytest.fail(f"Invalid JSON in stdout: {line}")

    proc.wait()
    assert proc.returncode == 0, f"Worker failed, stderr: {proc.stderr.read()}"

    types = [e["type"] for e in events]
    assert "STARTED" in types
    assert "PROGRESS" in types
    assert "COMPLETED" in types
    assert "FAILED" not in types

    assert dest.exists()


def test_worker_invalid_fingerprint(mock_pdf, tmp_path):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    req = ExportRequest(
        source_path=str(src),
        destination_path=str(dest),
        expected_fingerprint=PdfFingerprint(sha256="wrong_sha", size=size, page_count=1),
        specs=(
            ExportRegionSpec("r1", 1, Rect(10, 10, 100, 100), "T", "helv", 12.0, (0, 0, 0), (255, 255, 255)),
        ),
    )

    payload = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": "EXPORT_REQUEST",
        "job_id": "job123",
        "payload": json.loads(serialize_export_request(req)),
    }
    req_json = json.dumps(payload) + "\n"

    proc = subprocess.Popen(
        _get_worker_cmd(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proc.stdout.readline()
    proc.stdin.write(req_json)
    proc.stdin.flush()
    proc.wait()

    assert proc.returncode == 2  # FAILED
    stdout_out = proc.stdout.read()
    assert "SOURCE_FINGERPRINT_MISMATCH" in stdout_out


@pytest.mark.integration
def test_worker_cancel_protocol_error(mock_pdf, tmp_path):
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    specs = []
    for i in range(100):
        specs.append(
            ExportRegionSpec(
                f"r{i}", 1, Rect(10, 10, 50, 50), "Cancel me", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            )
        )

    req = ExportRequest(str(src), str(dest), PdfFingerprint(sha, size, 1), tuple(specs))

    payload = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": "EXPORT_REQUEST",
        "job_id": "job-cancel-proto",
        "payload": json.loads(serialize_export_request(req)),
    }

    proc = subprocess.Popen(
        _get_worker_cmd(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    proc.stdout.readline()  # READY
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()

    events = []

    def read_stdout():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            evt = json.loads(line)
            events.append(evt)
            if evt["type"] == "PROGRESS" and evt["payload"]["completed_regions"] > 0:
                # Send malformed CANCEL (missing job_id)
                cancel_payload = {
                    "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
                    "type": "CANCEL",
                }
                proc.stdin.write(json.dumps(cancel_payload) + "\n")
                proc.stdin.flush()

    t = threading.Thread(target=read_stdout)
    t.start()
    proc.wait(timeout=10)
    t.join()

    # The requirement is that it finishes with 4 (Protocol error)
    if proc.returncode != 4:
        pytest.fail(f"Expected 4, got {proc.returncode}")

    types = [e["type"] for e in events]
    assert "FAILED" in types

    failed_event = next(e for e in events if e["type"] == "FAILED")
    assert failed_event["payload"]["error_code"] == "PROTOCOL_ERROR"


@pytest.mark.integration
def test_worker_translated_text_leak(mock_pdf, tmp_path):
    from src.application.dtos.export import ExportRequest, PdfFingerprint, ExportRegionSpec
    from src.domain.value_objects.geometry import Rect
    from src.infrastructure.process.serialization import serialize_export_request
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION
    import json
    import subprocess
    
    src, sha, size = mock_pdf
    dest = tmp_path / "dest.pdf"

    secret_marker = "SUPER_SECRET_MARKER_12345"

    # We make a request with a bounding box outside the cropbox so it intentionally fails validation,
    # but contains the secret marker as translated text.
    req = ExportRequest(
        source_path=str(src),
        destination_path=str(dest),
        expected_fingerprint=PdfFingerprint(sha, size, 1),
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(-1000, -1000, -900, -900), secret_marker, "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    payload = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": "EXPORT_REQUEST",
        "job_id": "job-leak",
        "payload": json.loads(serialize_export_request(req)),
    }

    import sys
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.workers.pdf_export_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proc.stdout.readline()
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    proc.wait()

    stdout_out = proc.stdout.read()
    stderr_out = proc.stderr.read()

    assert proc.returncode == 2 # FAILED
    assert "INVALID_REQUEST" in stdout_out
    assert secret_marker not in stdout_out
    assert secret_marker not in stderr_out

@pytest.mark.integration
def test_controller_cancel_cleanup_ipc_synthetic(qapp):
    from src.application.dtos.export_ipc import EXPORT_IPC_PROTOCOL_VERSION, WorkerMessageType
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    controller = ExportProcessController()
    controller._state = ExportProcessState.RUNNING
    controller._current_job_id = "job-synth"

    received_payload = None

    def on_cancelled(job_id, payload):
        nonlocal received_payload
        received_payload = payload

    controller.cancelled.connect(on_cancelled)

    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": WorkerMessageType.CANCELLED.value,
        "job_id": "job-synth",
        "payload": {"cleanup_failed": True, "temporary_path": "some/path.tmp"},
    }

    controller._handle_event(evt)

    assert controller.state == ExportProcessState.CANCELLED
    assert received_payload is not None
    assert received_payload.cleanup_failed is True
    assert received_payload.temporary_path == "some/path.tmp"


@pytest.mark.integration
def test_controller_success(mock_pdf, tmp_path, qapp):
    from src.infrastructure.process.export_controller import (
        ExportProcessController,
        ExportProcessState,
    )

    src, sha, size = mock_pdf
    dest = tmp_path / "dest_controller.pdf"

    req = ExportRequest(
        source_path=str(src),
        destination_path=str(dest),
        expected_fingerprint=PdfFingerprint(sha256=sha, size=size, page_count=1),
        specs=(
            ExportRegionSpec(
                "r1", 1, Rect(10, 10, 100, 100), "Success", "helv", 12.0, (0, 0, 0), (255, 255, 255)
            ),
        ),
    )

    controller = ExportProcessController()

    events_received = []

    def on_progress(job_id, prog):
        events_received.append(("PROGRESS", prog.stage.name))

    def on_completed(job_id, result):
        events_received.append(("COMPLETED", result.destination_path))

    controller.progress.connect(on_progress)
    controller.completed.connect(on_completed)

    controller.start("job_ctrl_1", req)

    # Wait for process to finish using QCoreApplication.processEvents()
    import time

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

    assert controller.state == ExportProcessState.COMPLETED
    assert dest.exists()
    assert ("COMPLETED", str(dest)) in events_received
