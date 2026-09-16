import json
import logging
import sys
import threading
from typing import Any

# Redirect stdout to stderr to prevent library warnings (like PyMuPDF's fitz deprecation) from breaking IPC
_stdout = sys.stdout
sys.stdout = sys.stderr
try:
    from src.application.dtos.export_ipc import (
        EXPORT_IPC_PROTOCOL_VERSION,
        ProtocolError,
        WorkerCommandType,
        WorkerMessageType,
    )
    from src.application.errors.export import (
        ExportError,
        ExportFileError,
        ExportValidationError,
        InvalidExportRequestError,
        SourceFingerprintMismatchError,
    )
    from src.application.ports.export_progress import (
        ExportCancelledError,
        ExportExecutionContext,
        ExportProgress,
        ICancellationToken,
        IExportObserver,
    )
    from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter
    from src.infrastructure.process.serialization import (
        deserialize_export_request,
        serialize_export_result,
        strict_json_loads,
    )
finally:
    sys.stdout = _stdout


# Setup logging purely to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class IPCExportObserver(IExportObserver):
    def __init__(self, job_id: str):
        self.job_id = job_id

    def on_progress(self, progress: ExportProgress) -> None:
        emit_event(
            WorkerMessageType.PROGRESS,
            self.job_id,
            {
                "stage": progress.stage.name,
                "completed_regions": progress.completed_regions,
                "total_regions": progress.total_regions,
                "completed_pages": progress.completed_pages,
                "total_pages": progress.total_pages,
            },
        )


class StdinCancellationToken(ICancellationToken):
    def __init__(self):
        self._is_cancelled = threading.Event()
        self._protocol_error = threading.Event()

    def cancel(self):
        self._is_cancelled.set()

    def flag_protocol_error(self):
        self._protocol_error.set()
        # Cancelling allows graceful exit so we can emit FAILED
        self._is_cancelled.set()

    def throw_if_cancelled(self) -> None:
        if self._protocol_error.is_set():
            raise ExportCancelledError("PROTOCOL_ERROR")
        if self._is_cancelled.is_set():
            raise ExportCancelledError("CANCELLED")


def emit_event(
    msg_type: WorkerMessageType, job_id: str | None, payload: dict[str, Any] | None = None
):
    evt = {
        "protocol_version": EXPORT_IPC_PROTOCOL_VERSION,
        "type": msg_type.value,
        "job_id": job_id,
        "payload": payload or {},
    }
    sys.stdout.write(json.dumps(evt, allow_nan=False) + "\n")
    sys.stdout.flush()


def map_error_to_code(exc: Exception) -> str:
    if isinstance(exc, InvalidExportRequestError):
        return "INVALID_REQUEST"
    if isinstance(exc, SourceFingerprintMismatchError):
        return "SOURCE_FINGERPRINT_MISMATCH"
    if isinstance(exc, ExportValidationError):
        return "VALIDATION_FAILED"
    if isinstance(exc, ExportFileError):
        return "FILE_IO_ERROR"
    if isinstance(exc, ExportError):
        return "EXPORT_ERROR"
    return "UNKNOWN_EXPORT_ERROR"


def _command_reader_loop(token: StdinCancellationToken, current_job_id: str):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = strict_json_loads(line)
            if type(cmd) is not dict:
                raise ProtocolError("Command must be a JSON object")

            allowed_keys = {"protocol_version", "type", "job_id", "payload"}
            unknown_keys = set(cmd.keys()) - allowed_keys
            if unknown_keys:
                raise ProtocolError(f"Unknown fields in envelope: {unknown_keys}")

            if cmd.get("protocol_version") != EXPORT_IPC_PROTOCOL_VERSION:
                raise ProtocolError("Unknown protocol version in command")
            if cmd.get("type") == WorkerCommandType.CANCEL.value:
                # Validate exact job_id match
                if "job_id" not in cmd:
                    raise ProtocolError("Missing job_id in CANCEL command")
                if cmd["job_id"] != current_job_id:
                    raise ProtocolError("Mismatched job_id in CANCEL command")
                token.cancel()
            else:
                raise ProtocolError("Unknown command type")
        except ProtocolError:
            token.flag_protocol_error()
        except Exception:
            token.flag_protocol_error()


def _emit_protocol_error(job_id: str | None, msg: str) -> int:
    payload = {"error_code": "PROTOCOL_ERROR", "message": msg}
    emit_event(WorkerMessageType.FAILED, job_id, payload)
    return 4


def main() -> int:
    job_id = None
    try:
        emit_event(WorkerMessageType.READY, job_id)

        req_line = sys.stdin.readline().strip()
        if not req_line:
            return _emit_protocol_error(job_id, "Empty request line")

        try:
            req_json = strict_json_loads(req_line)
        except ProtocolError as e:
            return _emit_protocol_error(job_id, str(e))

        if type(req_json) is not dict:
            return _emit_protocol_error(job_id, "Envelope must be a JSON object")

        allowed_keys = {"protocol_version", "type", "job_id", "payload"}
        unknown_keys = set(req_json.keys()) - allowed_keys
        if unknown_keys:
            return _emit_protocol_error(job_id, f"Unknown fields in envelope: {unknown_keys}")

        if req_json.get("protocol_version") != EXPORT_IPC_PROTOCOL_VERSION:
            return _emit_protocol_error(
                job_id, f"Unknown protocol version: {req_json.get('protocol_version')}"
            )

        if req_json.get("type") != WorkerCommandType.EXPORT_REQUEST.value:
            return _emit_protocol_error(job_id, "First message must be EXPORT_REQUEST")

        if "job_id" not in req_json or type(req_json["job_id"]) is not str:
            return _emit_protocol_error(job_id, "Missing or invalid job_id in envelope")

        job_id = req_json["job_id"]

        if "payload" not in req_json or type(req_json["payload"]) is not dict:
            return _emit_protocol_error(job_id, "Missing or invalid payload in envelope")

        payload = req_json["payload"]

        # Deserialize request
        request_dto = deserialize_export_request(json.dumps(payload))

        # 2. Start command reader thread
        cancel_token = StdinCancellationToken()
        cmd_thread = threading.Thread(
            target=_command_reader_loop, args=(cancel_token, job_id), daemon=True
        )
        cmd_thread.start()

        # 3. Emit STARTED
        emit_event(WorkerMessageType.STARTED, job_id)

        # 4. Execute
        exporter = PyMuPDFVectorFormPdfExporter()
        observer = IPCExportObserver(job_id)
        context = ExportExecutionContext(observer=observer, cancellation_token=cancel_token)

        result = exporter.export(request_dto, context)

        # 5. Emit COMPLETED
        emit_event(
            WorkerMessageType.COMPLETED,
            job_id,
            json.loads(serialize_export_result(result)),
        )
        return 0

    except ProtocolError as e:
        return _emit_protocol_error(job_id, str(e))

    except ExportCancelledError as e:
        if cancel_token._protocol_error.is_set():
            return _emit_protocol_error(job_id, "Invalid IPC command received after startup")

        payload = {
            "cleanup_failed": getattr(e, "cleanup_failed", False),
            "temporary_path": getattr(e, "temporary_path", None),
        }
        emit_event(WorkerMessageType.CANCELLED, job_id, payload)
        return 3

    except ExportError as e:
        logger.error(f"Export failed: {e}")

        # Don't leak translation text
        msg = str(e)
        if "Translated text validation failed for region" in msg:
            pass  # Already sanitized by exporter
        elif "Text token" in msg:
            # Safety fallback, though exporter should handle this
            msg = "Translated text validation failed for region."

        payload = {
            "error_code": map_error_to_code(e),
            "message": msg,
            "cleanup_failed": getattr(e, "cleanup_failed", False),
            "temporary_path": getattr(e, "temporary_path", None),
        }
        emit_event(WorkerMessageType.FAILED, job_id, payload)
        return 2

    except Exception:
        logger.exception("Unexpected error in worker")
        payload = {
            "error_code": "UNKNOWN_EXPORT_ERROR",
            "message": "Unexpected internal error",
            "cleanup_failed": False,
            "temporary_path": None,
        }
        emit_event(WorkerMessageType.FAILED, job_id, payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
