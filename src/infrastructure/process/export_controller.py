import json
import logging
import sys
from collections import deque
from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QByteArray, QObject, QProcess, Signal

from src.application.dtos.export import ExportRequest, ExportResult
from src.application.dtos.export_ipc import (
    EXPORT_IPC_PROTOCOL_VERSION,
    ExportCancellationPayload,
    ExportWorkerErrorPayload,
    WorkerCommandType,
    WorkerMessageType,
)
from src.application.ports.export_progress import ExportProgress, ExportStage
from src.infrastructure.process.serialization import (
    deserialize_export_result,
    deserialize_progress,
    serialize_export_request,
    strict_json_loads,
)

logger = logging.getLogger(__name__)


class ExportProcessState(Enum):
    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    CANCELLING = auto()
    FINALIZING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    CRASHED = auto()


class ExportWorkerLauncher:
    def get_command(self) -> tuple[str, list[str]]:
        from src.application.runtime import is_frozen
        if is_frozen():
            # In frozen environment, re-invoke the executable
            return sys.executable, ["--worker", "export"]
        else:
            # In dev, we use sys.executable and run the module
            return sys.executable, ["-m", "src.main", "--worker", "export"]


class ExportProcessController(QObject):
    started = Signal(str)  # job_id
    progress = Signal(str, ExportProgress)  # job_id, progress
    finalizing = Signal(str)  # job_id
    completed = Signal(str, ExportResult)  # job_id, result
    cancelled = Signal(str, ExportCancellationPayload)  # job_id, payload
    failed = Signal(str, ExportWorkerErrorPayload)  # job_id, error
    crashed = Signal(str, dict)  # job_id, crash_info

    def __init__(self, launcher: ExportWorkerLauncher | None = None):
        super().__init__()
        self._launcher = launcher or ExportWorkerLauncher()
        self._state = ExportProcessState.IDLE
        self._process: QProcess | None = None
        self._current_job_id: str | None = None
        self._pending_request: ExportRequest | None = None
        self._stderr_buffer: deque[str] = deque(maxlen=100)

        self._last_stage: ExportStage | None = None
        self._last_progress: ExportProgress | None = None
        self._last_error_code: str | None = None
        self._terminal_event_emitted: bool = False
        self._force_terminated: bool = False
        self._final_destination_path: str | None = None
        self._temp_destination_path: str | None = None

    @property
    def is_active(self) -> bool:
        return self._state in (
            ExportProcessState.STARTING,
            ExportProcessState.RUNNING,
            ExportProcessState.CANCELLING,
            ExportProcessState.FINALIZING,
        )

    @property
    def state(self) -> ExportProcessState:
        return self._state

    def reset(self):
        if self.is_active:
            raise RuntimeError("Cannot reset while active")
        self._state = ExportProcessState.IDLE
        self._current_job_id = None
        self._pending_request = None
        self._stderr_buffer.clear()
        self._last_stage = None
        self._last_progress = None
        self._last_error_code = None
        self._terminal_event_emitted = False
        self._force_terminated = False
        if self._process:
            self._process.deleteLater()
            self._process = None

    def start(self, job_id: str, request: ExportRequest):
        if self.is_active:
            raise RuntimeError("An export is already active.")

        self.reset()
        self._state = ExportProcessState.STARTING
        self._current_job_id = job_id

        import os
        import uuid
        import dataclasses
        dest_dir = os.path.dirname(request.destination_path)
        dest_name = os.path.basename(request.destination_path)
        temp_name = f".{dest_name}.traductor-export-{uuid.uuid4().hex[:8]}.tmp.pdf"
        temp_path = os.path.join(dest_dir, temp_name)
        
        self._final_destination_path = request.destination_path
        self._temp_destination_path = temp_path
        
        self._pending_request = dataclasses.replace(request, destination_path=temp_path)

        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_ready_read_stdout)
        self._process.readyReadStandardError.connect(self._on_ready_read_stderr)
        self._process.finished.connect(self._on_process_finished)

        cmd, args = self._launcher.get_command()
        self._process.start(cmd, args)
        # We wait for READY before sending the request

    def cancel(self):
        if self._state not in (ExportProcessState.STARTING, ExportProcessState.RUNNING):
            return

        self._state = ExportProcessState.CANCELLING
        if self._process and self._process.state() == QProcess.Running:
            payload = {
                "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
                "type": WorkerCommandType.CANCEL.value,
                "job_id": self._current_job_id,
            }
            cancel_bytes = (json.dumps(payload) + "\n").encode("utf-8")
            self._process.write(cancel_bytes)

    def force_stop(self):
        if not self.is_active:
            return
        if self._state == ExportProcessState.FINALIZING:
            return

        if self._process and self._process.state() == QProcess.Running:
            self._process.kill()

    def _parse_payload_cancelled(self, payload: dict[str, Any]) -> ExportCancellationPayload:
        allowed = {"cleanup_failed", "temporary_path"}
        unknown = set(payload.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown fields in CANCELLED payload: {unknown}")
        if "cleanup_failed" not in payload or "temporary_path" not in payload:
            raise ValueError("Missing required fields in CANCELLED payload")
        if not isinstance(payload["cleanup_failed"], bool):
            raise ValueError("cleanup_failed must be bool")
        if payload["temporary_path"] is not None and not isinstance(payload["temporary_path"], str):
            raise ValueError("temporary_path must be str or None")
        return ExportCancellationPayload(
            cleanup_failed=payload["cleanup_failed"], temporary_path=payload["temporary_path"]
        )

    def _parse_payload_failed(self, payload: dict[str, Any]) -> ExportWorkerErrorPayload:
        allowed = {"error_code", "message", "cleanup_failed", "temporary_path"}
        unknown = set(payload.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown fields in FAILED payload: {unknown}")
        if (
            "error_code" not in payload
            or "message" not in payload
            or "cleanup_failed" not in payload
            or "temporary_path" not in payload
        ):
            raise ValueError("Missing required fields in FAILED payload")
        if not isinstance(payload["error_code"], str):
            raise ValueError("error_code must be str")
        if not isinstance(payload["message"], str):
            raise ValueError("message must be str")
        if not isinstance(payload["cleanup_failed"], bool):
            raise ValueError("cleanup_failed must be bool")
        if payload["temporary_path"] is not None and not isinstance(payload["temporary_path"], str):
            raise ValueError("temporary_path must be str or None")
        return ExportWorkerErrorPayload(
            error_code=payload["error_code"],
            message=payload["message"],
            cleanup_failed=payload["cleanup_failed"],
            temporary_path=payload["temporary_path"],
        )

    def _on_ready_read_stdout(self):
        if not self._process:
            return

        while self._process.canReadLine():
            line_bytes: QByteArray = self._process.readLine()
            line = line_bytes.data().decode("utf-8").strip()
            if not line:
                continue

            try:
                evt = strict_json_loads(line)
                self._handle_event(evt)
            except Exception as e:
                logger.error(f"Failed to parse IPC event: {line} - {e}")
                # Protocol error, force fail
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", "Failed to parse stdout from worker"
                )

    def _on_ready_read_stderr(self):
        if not self._process:
            return
        err_bytes = self._process.readAllStandardError()
        text = err_bytes.data().decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.strip():
                self._stderr_buffer.append(line.strip())
                logger.debug(f"[WORKER] {line.strip()}")

    def _handle_event(self, evt: dict[str, Any]):
        if type(evt) is not dict:
            self._force_crash_or_protocol_error("PROTOCOL_ERROR", "Event envelope is not a dict")
            return

        allowed_keys = {"protocol_version", "type", "job_id", "payload"}
        unknown_keys = set(evt.keys()) - allowed_keys
        if unknown_keys:
            self._force_crash_or_protocol_error(
                "PROTOCOL_ERROR", f"Unknown fields in event: {unknown_keys}"
            )
            return

        if evt.get("protocol_version") != EXPORT_IPC_PROTOCOL_VERSION:
            self._force_crash_or_protocol_error("PROTOCOL_ERROR", "Unknown protocol version")
            return

        msg_type_str = evt.get("type")
        job_id = evt.get("job_id")

        payload = evt.get("payload", {})
        if not isinstance(payload, dict):
            self._force_crash_or_protocol_error("PROTOCOL_ERROR", "Payload must be a dict")
            return

        if self._terminal_event_emitted:
            return

        try:
            msg_type = WorkerMessageType(msg_type_str)
        except ValueError:
            self._force_crash_or_protocol_error(
                "PROTOCOL_ERROR", f"Unknown message type: {msg_type_str}"
            )
            return

        if msg_type == WorkerMessageType.READY:
            if self._state != ExportProcessState.STARTING:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", "READY received outside of STARTING"
                )
                return
            if job_id is not None:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", "READY must not have a job_id"
                )
                return
            if payload != {}:
                self._force_crash_or_protocol_error("PROTOCOL_ERROR", "READY payload must be empty")
                return

            req_payload = {
                "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
                "type": WorkerCommandType.EXPORT_REQUEST.value,
                "job_id": self._current_job_id,
                "payload": json.loads(serialize_export_request(self._pending_request)),
            }
            req_bytes = (json.dumps(req_payload, allow_nan=False) + "\n").encode("utf-8")
            self._process.write(req_bytes)
            self._pending_request = None
            return

        # We enforce matching job_id for events after READY
        if job_id != self._current_job_id:
            self._force_crash_or_protocol_error(
                "PROTOCOL_ERROR", f"Received event for wrong job_id: {job_id}"
            )
            return

        if msg_type == WorkerMessageType.STARTED:
            if payload != {}:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", "STARTED payload must be empty"
                )
                return
            self._state = ExportProcessState.RUNNING
            self.started.emit(job_id)

        elif msg_type == WorkerMessageType.PROGRESS:
            try:
                prog = deserialize_progress(json.dumps(payload, allow_nan=False))
            except Exception as e:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", f"Invalid progress payload: {e}"
                )
                return

            if self._state == ExportProcessState.STARTING:
                self._state = ExportProcessState.RUNNING

            self._last_progress = prog
            self._last_stage = prog.stage

            if prog.stage == ExportStage.FINALIZING:
                self._state = ExportProcessState.FINALIZING
                self.finalizing.emit(job_id)
            else:
                self.progress.emit(job_id, prog)

        elif msg_type == WorkerMessageType.COMPLETED:
            try:
                res = deserialize_export_result(json.dumps(payload, allow_nan=False))
            except Exception as e:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", f"Invalid COMPLETED payload: {e}"
                )
                return
                
            import os
            import pymupdf as fitz
            import dataclasses
            
            temp_path = self._temp_destination_path
            final_path = self._final_destination_path
            
            if not temp_path or not os.path.exists(temp_path):
                self._force_crash_or_protocol_error("PROTOCOL_ERROR", "Exported temp file is missing")
                return
                
            try:
                if os.path.getsize(temp_path) == 0:
                    raise RuntimeError("Exported file is empty")
                    
                doc = fitz.open(temp_path)
                page_count = doc.page_count
                doc.close()
                
                # Atomic replace
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.replace(temp_path, final_path)
            except Exception as e:
                self._cleanup_temp_file()
                self._force_crash_or_protocol_error("REPLACE_ERROR", f"Validation or replace failed: {e}")
                return
                
            res = dataclasses.replace(res, destination_path=final_path)
            
            self._state = ExportProcessState.COMPLETED
            self._terminal_event_emitted = True
            self.completed.emit(job_id, res)

        elif msg_type == WorkerMessageType.CANCELLED:
            if self._state == ExportProcessState.FINALIZING:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", "CANCELLED received during FINALIZING"
                )
                return
            try:
                cancellation_payload = self._parse_payload_cancelled(payload)
            except Exception as e:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", f"Invalid CANCELLED payload: {e}"
                )
                return
            self._state = ExportProcessState.CANCELLED
            self._terminal_event_emitted = True
            self._cleanup_temp_file()
            self.cancelled.emit(job_id, cancellation_payload)

        elif msg_type == WorkerMessageType.FAILED:
            try:
                err = self._parse_payload_failed(payload)
            except Exception as e:
                self._force_crash_or_protocol_error(
                    "PROTOCOL_ERROR", f"Invalid FAILED payload: {e}"
                )
                return
            self._state = ExportProcessState.FAILED
            self._terminal_event_emitted = True
            self._last_error_code = err.error_code
            self._cleanup_temp_file()
            self.failed.emit(job_id, err)

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        sender = self.sender()
        if sender and sender != self._process:
            return

        if self._force_terminated:
            # We already handled this as a terminal event and killed it
            return

        if not self._terminal_event_emitted:
            # Process crashed or died without terminal event
            self._state = ExportProcessState.CRASHED
            crash_info = {
                "exit_code": exit_code,
                "exit_status": exit_status.value,
                "last_stage": self._last_stage.name if self._last_stage else None,
                "stderr_tail": list(self._stderr_buffer),
                "reason": "Process exited without emitting a terminal event",
            }
            self._cleanup_temp_file()
            self.crashed.emit(self._current_job_id, crash_info)
            return

        # Verify exit code consistency
        inconsistency = None
        if self._state == ExportProcessState.COMPLETED and exit_code != 0:
            inconsistency = "COMPLETED event but exit_code != 0"
        elif self._state == ExportProcessState.CANCELLED and exit_code != 3:
            inconsistency = "CANCELLED event but exit_code != 3"
        elif self._state == ExportProcessState.FAILED:
            if self._last_error_code == "PROTOCOL_ERROR" and exit_code != 4:
                inconsistency = f"FAILED(PROTOCOL_ERROR) but exit_code {exit_code} != 4"
            elif self._last_error_code != "PROTOCOL_ERROR" and exit_code != 2:
                inconsistency = f"FAILED({self._last_error_code}) but exit_code {exit_code} != 2"

        if inconsistency:
            self._state = ExportProcessState.CRASHED
            crash_info = {
                "exit_code": exit_code,
                "exit_status": exit_status.value,
                "last_stage": self._last_stage.name if self._last_stage else None,
                "stderr_tail": list(self._stderr_buffer),
                "reason": inconsistency,
            }
            self._cleanup_temp_file()
            self.crashed.emit(self._current_job_id, crash_info)

    def _force_crash_or_protocol_error(self, code: str, msg: str):
        if self._terminal_event_emitted:
            return
        self._terminal_event_emitted = True
        self._force_terminated = True
        if self._process and self._process.state() == QProcess.Running:
            self._process.kill()

        self._state = ExportProcessState.FAILED
        err = ExportWorkerErrorPayload(error_code=code, message=msg)
        self._cleanup_temp_file()
        self.failed.emit(self._current_job_id, err)

    def _cleanup_temp_file(self):
        import os
        if self._temp_destination_path and os.path.exists(self._temp_destination_path):
            try:
                os.remove(self._temp_destination_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {self._temp_destination_path}: {e}")
