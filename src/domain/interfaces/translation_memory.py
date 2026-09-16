from abc import ABC, abstractmethod
from typing import Sequence
from src.domain.models.translation_memory import TranslationMemoryEntry

class ITranslationMemoryRepository(ABC):
    @abstractmethod
    def get_by_project_and_hash(self, project_id: str, target_language: str, source_hash: str) -> Sequence[TranslationMemoryEntry]:
        pass

    @abstractmethod
    def upsert(self, entry: TranslationMemoryEntry):
        pass

    @abstractmethod
    def delete_for_region(self, region_id: str):
        pass
