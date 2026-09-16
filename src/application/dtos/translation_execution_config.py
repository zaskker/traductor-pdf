from dataclasses import dataclass, field
from src.domain.interfaces.translation import ITranslationEngine
from src.domain.models.glossary import GlossaryEntry

@dataclass
class TranslationExecutionConfig:
    source_language: str
    target_language: str
    engine: ITranslationEngine
    
    # Immutable glossary entries snapshot
    glossary_id: str | None = None
    glossary_revision: int | None = None
    glossary_entries: list[GlossaryEntry] = field(default_factory=list)
