from dataclasses import dataclass
from datetime import datetime

@dataclass
class TranslationMemoryEntry:
    entry_id: str
    project_id: str
    source_text: str
    source_normalized: str
    source_hash: str
    target_text: str
    target_language: str
    region_id: str
    block_id: str
    translation_revision: int
    approved_at: datetime
    glossary_id: str | None = None
    glossary_revision: int | None = None
    original_translation_engine: str | None = None
    original_translation_model: str | None = None
