import copy
import re
import uuid
from datetime import UTC, datetime
from src.application.services.block_grouper import group_source_fragments_into_blocks

from src.domain.interfaces.persistence import ITranslationRegionRepository
from src.domain.models.region import TranslationRegion


class EditTranslationUseCase:
    """
    Construye y valida snapshots para una edición manual de traducción.
    No interactúa con la persistencia ni con Ollama; delega al ViewModel
    la orquestación del EditTranslationCommand y el CommandHistory.
    """

    def __init__(self, repository: ITranslationRegionRepository):
        self.repository = repository

    def execute(self, region_id: str, new_text: str) -> tuple[TranslationRegion, TranslationRegion]:
        if not new_text or not new_text.strip():
            raise ValueError("Translated text cannot be empty.")

        old_region = self.repository.get(region_id)
        if not old_region:
            raise ValueError(f"Region {region_id} not found.")

        if not old_region.source_text or not old_region.source_text.strip():
            raise ValueError("Region source text is empty. Cannot edit translation.")

        # Copiar para no mutar instancias del repositorio/caché.
        old_region_snapshot = copy.deepcopy(old_region)

        # Construir nuevo snapshot con is_manually_edited y nuevo texto.
        new_region_snapshot = copy.deepcopy(old_region_snapshot)
        new_region_snapshot.translated_text = new_text
        new_region_snapshot.is_manually_edited = True
        new_region_snapshot.updated_at = datetime.now(UTC)

        if not new_region_snapshot.translation_revision:
            new_region_snapshot.translation_revision = 1
        else:
            new_region_snapshot.translation_revision += 1

        source_blocks = group_source_fragments_into_blocks(new_region_snapshot.source_fragments)
        old_blocks = old_region_snapshot.translated_blocks or []

        if len(source_blocks) <= 1:
            split_texts = [new_text.strip()]
        else:
            split_texts = [b.strip() for b in re.split(r'\n\s*\n', new_text.strip())]

        new_translated_blocks = []
        if len(split_texts) == len(old_blocks) and len(old_blocks) > 0:
            for i, stext in enumerate(split_texts):
                new_translated_blocks.append({
                    "id": old_blocks[i]["id"],
                    "source_block_index": old_blocks[i].get("source_block_index", -1),
                    "text": stext
                })
        else:
            if len(split_texts) == len(source_blocks):
                for i, stext in enumerate(split_texts):
                    new_translated_blocks.append({
                        "id": uuid.uuid4().hex,
                        "source_block_index": source_blocks[i].block_index,
                        "text": stext
                    })
            else:
                for i, stext in enumerate(split_texts):
                    new_translated_blocks.append({
                        "id": uuid.uuid4().hex,
                        "source_block_index": -1,
                        "text": stext
                    })
                    
        new_region_snapshot.translated_blocks = new_translated_blocks

        return old_region_snapshot, new_region_snapshot
