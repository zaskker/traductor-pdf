import copy
from datetime import UTC, datetime

from src.domain.interfaces.persistence import IUnitOfWork
from src.domain.interfaces.translation import StaleTranslationRevisionError, TranslationNotReviewedError
from src.domain.models.enums import ReviewStatus
from src.domain.models.region import TranslationRegion
from src.domain.models.translation_memory import TranslationMemoryEntry
from src.domain.services.translation_memory_utils import normalize_source_text, hash_source_text
from src.application.services.block_grouper import group_source_fragments_into_blocks


class ApproveTranslationUseCase:
    """
    Approves a reviewed translation as the final version.

    Preconditions:
    - The region must have a valid translation (translation_revision is not None).
    - The expected_translation_revision must match the current translation_revision.
      If not, StaleTranslationRevisionError is raised.
    - The region must be in REVIEWED state (reviewed_translation_revision == translation_revision).
      If not, TranslationNotReviewedError is raised.
      Flow must be: UNREVIEWED -> mark_reviewed -> REVIEWED -> approve -> APPROVED.

    Effect:
    - Sets approved_translation_revision = translation_revision
    - Sets approved_at = now(UTC)

    Does NOT modify: translated_text, translation_revision, engine/glossary metadata,
    reviewed_translation_revision, reviewed_at.

    Review/Approval are NOT undoable workflow steps.
    """

    def __init__(self, uow: 'IUnitOfWork'):
        self.uow = uow

    def execute(
        self, region_id: str, expected_translation_revision: int
    ) -> tuple[TranslationRegion, TranslationRegion]:
        with self.uow:
            region = self.uow.region_repository.get(region_id)
            if not region:
                raise ValueError(f"Region {region_id} not found.")

            if region.translation_revision is None:
                raise ValueError(
                    f"Region {region_id} has no valid translation - cannot approve."
                )

            if region.translation_revision != expected_translation_revision:
                raise StaleTranslationRevisionError(
                    f"Expected translation_revision={expected_translation_revision} "
                    f"but current is {region.translation_revision}. Refresh and retry."
                )

            if region.review_status not in (ReviewStatus.REVIEWED, ReviewStatus.APPROVED):
                raise TranslationNotReviewedError(
                    f"Region {region_id} must be REVIEWED before it can be APPROVED. "
                    f"Current status: {region.review_status.name}. "
                    f"Call MarkTranslationReviewedUseCase first."
                )

            old_snapshot = copy.deepcopy(region)

            new_snapshot = copy.deepcopy(region)
            new_snapshot.approved_translation_revision = region.translation_revision
            new_snapshot.approved_at = datetime.now(UTC)

            self.uow.region_repository.save(new_snapshot)
            
            # Corpus Update
            self.uow.translation_memory_repository.delete_for_region(region_id)
            
            if new_snapshot.source_fragments and new_snapshot.translated_blocks:
                source_blocks = group_source_fragments_into_blocks(new_snapshot.source_fragments)
                target_blocks_map = {tb.get("source_block_index"): tb for tb in new_snapshot.translated_blocks}
                
                for source_block in source_blocks:
                    tb = target_blocks_map.get(source_block.block_index)
                    if not tb or "text" not in tb:
                        continue
                    if tb.get("source_block_index") == -1: # Manual edit lost mapping
                        continue
                        
                    target_text = tb["text"]
                    if not target_text or not target_text.strip():
                        continue
                        
                    s_text = source_block.text
                    if not s_text or not s_text.strip():
                        continue
                        
                    s_norm = normalize_source_text(s_text)
                    s_hash = hash_source_text(s_norm)
                    block_id = tb.get("id", f"b_{source_block.block_index}")
                    
                    entry = TranslationMemoryEntry(
                        entry_id=f"{region_id}_{block_id}",
                        project_id=new_snapshot.project_id,
                        source_text=s_text,
                        source_normalized=s_norm,
                        source_hash=s_hash,
                        target_text=target_text,
                        target_language=new_snapshot.translation_options.get("target_language") if new_snapshot.translation_options else "es",
                        region_id=region_id,
                        block_id=block_id,
                        translation_revision=new_snapshot.translation_revision,
                        approved_at=new_snapshot.approved_at,
                        glossary_id=new_snapshot.glossary_id,
                        glossary_revision=new_snapshot.glossary_revision,
                        original_translation_engine="MANUAL" if new_snapshot.is_manually_edited else (new_snapshot.translation_options.get("translation_origin", new_snapshot.translation_engine) if new_snapshot.translation_options else new_snapshot.translation_engine),
                        original_translation_model=new_snapshot.translation_model
                    )
                    self.uow.translation_memory_repository.upsert(entry)

        return old_snapshot, new_snapshot
