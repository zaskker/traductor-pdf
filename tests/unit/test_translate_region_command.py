import copy

import pytest

from src.application.commands import TranslateRegionCommand
from src.domain.models.enums import RegionStatus
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect


class DummyErrorRepo:
    def __init__(self):
        self.fail_save = False
        self.regions = {}

    def save(self, region):
        if self.fail_save:
            raise ValueError("DB error")
        self.regions[region.id] = copy.deepcopy(region)

    def get(self, rid):
        return self.regions.get(rid)


@pytest.fixture
def repo():
    return DummyErrorRepo()


@pytest.fixture
def regions():
    old_r = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        translated_text="",
        status=RegionStatus.PENDING,
    )
    new_r = copy.deepcopy(old_r)
    new_r.translated_text = "Hola"
    new_r.status = RegionStatus.TRANSLATED
    return old_r, new_r


def test_translate_command_execute(repo, regions):
    old_r, new_r = regions
    cmd = TranslateRegionCommand(old_r, new_r, repo)
    cmd.execute()

    assert repo.get("reg_1").status == RegionStatus.TRANSLATED
    assert repo.get("reg_1").translated_text == "Hola"


def test_translate_command_undo(repo, regions):
    old_r, new_r = regions
    cmd = TranslateRegionCommand(old_r, new_r, repo)
    cmd.execute()
    cmd.undo()

    assert repo.get("reg_1").status == RegionStatus.PENDING
    assert repo.get("reg_1").translated_text == ""


def test_translate_command_redo(repo, regions):
    old_r, new_r = regions
    cmd = TranslateRegionCommand(old_r, new_r, repo)
    cmd.execute()
    cmd.undo()
    cmd.redo()

    assert repo.get("reg_1").status == RegionStatus.TRANSLATED
    assert repo.get("reg_1").translated_text == "Hola"


def test_translate_command_repo_failure(repo, regions):
    old_r, new_r = regions
    repo.fail_save = True
    cmd = TranslateRegionCommand(old_r, new_r, repo)

    with pytest.raises(Exception, match="DB error"):
        cmd.execute()

    assert repo.get("reg_1") is None  # Never saved
