import pytest

from src.application.commands import CommandExecutionError, EditTranslationCommand
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect


class MockFailingRepo:
    def __init__(self):
        self.regions = {}

    def get(self, region_id):
        return self.regions.get(region_id)

    def save(self, region):
        raise RuntimeError("Database error")


class MockRepo:
    def __init__(self):
        self.regions = {}

    def get(self, region_id):
        return self.regions.get(region_id)

    def save(self, region):
        self.regions[region.id] = region


def test_edit_translation_command_success():
    repo = MockRepo()
    old_region = TranslationRegion(
        id="test_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_text="Hello",
        translated_text="Hola",
    )
    new_region = TranslationRegion(
        id="test_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_text="Hello",
        translated_text="Hola editado",
        is_manually_edited=True,
    )

    cmd = EditTranslationCommand(old_region, new_region, repo)
    cmd.execute()

    assert repo.get("test_1").translated_text == "Hola editado"
    assert repo.get("test_1").is_manually_edited

    cmd.undo()
    assert repo.get("test_1").translated_text == "Hola"
    assert not repo.get("test_1").is_manually_edited

    cmd.redo()
    assert repo.get("test_1").translated_text == "Hola editado"
    assert repo.get("test_1").is_manually_edited


def test_edit_translation_command_failure():
    repo = MockFailingRepo()
    old_region = TranslationRegion(
        id="test_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_text="Hello",
        translated_text="Hola",
    )
    new_region = TranslationRegion(
        id="test_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
        source_text="Hello",
        translated_text="Hola editado",
        is_manually_edited=True,
    )

    cmd = EditTranslationCommand(old_region, new_region, repo)
    with pytest.raises(CommandExecutionError, match="Edit translation failed"):
        cmd.execute()

    assert not cmd._executed
