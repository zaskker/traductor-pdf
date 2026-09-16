from typing import Protocol

from src.application.dtos.export import (
    ExportRequest,
    ExportResult,
)
from src.application.ports.export_progress import ExportExecutionContext


class ITranslatedPdfExporter(Protocol):
    def export(
        self, request: ExportRequest, context: ExportExecutionContext | None = None
    ) -> ExportResult: ...
