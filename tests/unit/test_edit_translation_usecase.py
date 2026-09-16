from datetime import UTC, datetime

import pytest

from src.application.use_cases.edit_translation import EditTranslationUseCase
from src.domain.models.enums import RegionStatus
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect


class MockRepo:
    def __init__(self):
        self.regions = {}

    def get(self, region_id):
        return self.regions.get(region_id)

    def save(self, region):
        self.regions[region.id] = region


def test_edit_translation_success():
    repo = MockRepo()
    region = TranslationRegion(
        id="test_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_text="Hello",
        translated_text="Hola",
        status=RegionStatus.TRANSLATED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.save(region)

    use_case = EditTranslationUseCase(repo)
    old_snap, new_snap = use_case.execute("test_1", "Hola editado")

    # Old snapshot remains the same
    assert old_snap.id == "test_1"
    assert old_snap.translated_text == "Hola"
    assert not old_snap.is_manually_edited

    # New snapshot has edits
    assert new_snap.translated_text == "Hola editado"
    assert new_snap.is_manually_edited
    assert new_snap.updated_at > region.updated_at


def test_edit_translation_empty_text():
    repo = MockRepo()
    use_case = EditTranslationUseCase(repo)
    with pytest.raises(ValueError, match="Translated text cannot be empty"):
        use_case.execute("test_1", "   ")


def test_edit_translation_region_not_found():
    repo = MockRepo()
    use_case = EditTranslationUseCase(repo)
    with pytest.raises(ValueError, match="Region test_1 not found"):
        use_case.execute("test_1", "Hola")


def test_edit_translation_empty_source():
    repo = MockRepo()
    region = TranslationRegion(
        id="test_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_text="",
    )
    repo.save(region)

    use_case = EditTranslationUseCase(repo)
    with pytest.raises(ValueError, match="Region source text is empty"):
        use_case.execute("test_1", "Hola editado")
