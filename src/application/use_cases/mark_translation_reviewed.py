import copy
from datetime import UTC, datetime

from src.domain.interfaces.persistence import ITranslationRegionRepository
from src.domain.interfaces.translation import StaleTranslationRevisionError
from src.domain.models.region import TranslationRegion


class MarkTranslationReviewedUseCase:
    """
    Marks a translation as reviewed by the user.

    Preconditions:
    - The region must have a valid translation (translation_revision is not None).
    - The expected_translation_revision must match the current translation_revision.
      If not, StaleTranslationRevisionError is raised.

    Effect:
    - Sets reviewed_translation_revision = translation_revision
    - Sets reviewed_at = now(UTC)

    Does NOT modify: translated_text, translation_revision, engine/glossary metadata,
    approved_translation_revision, approved_at.

    Review/Approval are NOT undoable workflow steps.
    """

    def __init__(self, repository: ITranslationRegionRepository):
        self.repository = repository

    def execute(
        self, region_id: str, expected_translation_revision: int
    ) -> tuple[TranslationRegion, TranslationRegion]:
        region = self.repository.get(region_id)
        if not region:
            raise ValueError(f"Region {region_id} not found.")

        if region.translation_revision is None:
            raise ValueError(
                f"Region {region_id} has no valid translation - cannot mark as reviewed."
            )

        if region.translation_revision != expected_translation_revision:
            raise StaleTranslationRevisionError(
                f"Expected translation_revision={expected_translation_revision} "
                f"but current is {region.translation_revision}. Refresh and retry."
            )

        old_snapshot = copy.deepcopy(region)

        new_snapshot = copy.deepcopy(region)
        new_snapshot.reviewed_translation_revision = region.translation_revision
        new_snapshot.reviewed_at = datetime.now(UTC)

        self.repository.save(new_snapshot)

        return old_snapshot, new_snapshot
