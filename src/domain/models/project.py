from dataclasses import dataclass
from datetime import datetime


@dataclass
class Project:
    """Modelo del proyecto."""

    id: str
    name: str
    pdf_path: str
    pdf_sha256: str
    pdf_size: int
    pdf_page_count: int
    last_viewed_page: int
    created_at: datetime
    updated_at: datetime
    active_glossary_id: str | None = None

    def __post_init__(self):
        if self.pdf_size < 0:
            raise ValueError("pdf_size no puede ser negativo")
        if self.pdf_page_count < 0:
            raise ValueError("pdf_page_count no puede ser negativo")
        if self.last_viewed_page < 0:
            raise ValueError("last_viewed_page no puede ser negativo")
