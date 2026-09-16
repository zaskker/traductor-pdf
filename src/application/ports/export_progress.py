from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol


class ExportStage(Enum):
    VALIDATING = auto()
    PREPARING = auto()
    APPLYING = auto()
    SAVING = auto()
    VERIFYING = auto()
    FINALIZING = auto()
    COMPLETED = auto()


@dataclass(frozen=True)
class ExportProgress:
    stage: ExportStage
    completed_regions: int
    total_regions: int
    completed_pages: int
    total_pages: int

    def __post_init__(self):
        if not (0 <= self.completed_regions <= self.total_regions):
            raise ValueError(
                f"Invalid regions count: {self.completed_regions}/{self.total_regions}"
            )
        if not (0 <= self.completed_pages <= self.total_pages):
            raise ValueError(f"Invalid pages count: {self.completed_pages}/{self.total_pages}")


class IExportObserver(Protocol):
    def on_progress(self, progress: ExportProgress) -> None: ...


class ICancellationToken(Protocol):
    def throw_if_cancelled(self) -> None: ...


class ExportCancelledError(Exception):
    """Raised when an export operation is cooperatively cancelled."""

    def __init__(
        self, message: str, *, temporary_path: str | None = None, cleanup_failed: bool = False
    ):
        super().__init__(message)
        self.temporary_path = temporary_path
        self.cleanup_failed = cleanup_failed


@dataclass(frozen=True)
class ExportExecutionContext:
    observer: IExportObserver | None = None
    cancellation_token: ICancellationToken | None = None
