from typing import Protocol

from src.application.dtos.export import PdfSourceInspection


class IPdfSourceInspector(Protocol):
    def inspect(self, source_path: str) -> PdfSourceInspection: ...
