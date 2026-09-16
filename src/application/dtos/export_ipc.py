from dataclasses import dataclass, field
from enum import Enum
from typing import Any

EXPORT_IPC_PROTOCOL_VERSION = 3  # v3: Hotfix 4.1 Single-line wrapping, alignment, safe expansion


class WorkerMessageType(Enum):
    READY = "READY"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class WorkerCommandType(Enum):
    EXPORT_REQUEST = "EXPORT_REQUEST"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class ExportWorkerErrorPayload:
    error_code: str
    message: str
    cleanup_failed: bool = False
    temporary_path: str | None = None


@dataclass(frozen=True)
class ExportCancellationPayload:
    cleanup_failed: bool = False
    temporary_path: str | None = None


@dataclass(frozen=True)
class ExportWorkerEvent:
    protocol_version: int
    type: WorkerMessageType
    job_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)


class ProtocolError(Exception):
    pass
