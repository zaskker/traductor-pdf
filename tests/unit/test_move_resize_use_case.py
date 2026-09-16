from datetime import UTC, datetime

import pytest

from src.application.commands import MoveResizeRegionCommand
from src.application.ports.text_extractor import ITextExtractor
from src.application.services.text_extraction import TextExtractionService
from src.application.use_cases.move_resize_region import (
    MoveResizeRegionError,
    MoveResizeRegionUseCase,
)
from src.domain.interfaces.persistence import ITranslationRegionRepository
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import ExtractionMethod, TextExtractionResult
from src.domain.value_objects.geometry import Rect


class MockExtractor(ITextExtractor):
    def __init__(self):
        self.mock_result = None

    def extract(self, page_number: int, selection: Rect) -> TextExtractionResult:
        if self.mock_result is None:
            return TextExtractionResult(
                page_number=page_number,
                selection_rect=selection,
                source_bbox=Rect(0, 0, 0, 0),
                text="",
                fragments=(),
                extraction_method=ExtractionMethod.NONE,
                warnings=(),
            )
        return self.mock_result


class MockRepo(ITranslationRegionRepository):
    def __init__(self):
        self.regions = {}
        self.should_fail = False

    def save(self, region: TranslationRegion):
        if self.should_fail:
            raise RuntimeError("DB Error")
        self.regions[region.id] = region

    def get(self, id: str) -> TranslationRegion | None:
        return self.regions.get(id)

    def delete(self, id: str):
        self.regions.pop(id, None)

    def get_by_page(self, pid: str, page: int) -> list[TranslationRegion]:
        return []

    def get_all(self, pid: str) -> list[TranslationRegion]:
        return []

    def count(self, pid: str) -> int:
        return len(self.regions)


def test_move_snapshot_execute_undo_redo():
    repo = MockRepo()
    now = datetime.now(UTC)
    old_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_bbox=Rect(0, 0, 10, 10),
        source_text="TEXT A",
        source_fragments=(),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=now,
        updated_at=now,
    )
    repo.save(old_region)

    new_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(10, 10, 20, 20),
        source_bbox=Rect(10, 10, 20, 20),
        source_text="TEXT B",
        source_fragments=(),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=old_region.created_at,
        updated_at=datetime.now(UTC),
    )

    cmd = MoveResizeRegionCommand(old_region, new_region, repo)

    cmd.execute()
    assert repo.get("r1").source_text == "TEXT B"

    cmd.undo()
    assert repo.get("r1").source_text == "TEXT A"

    cmd.redo()
    assert repo.get("r1").source_text == "TEXT B"


def test_move_triggers_re_extraction():
    extractor = MockExtractor()
    service = TextExtractionService(extractor)
    use_case = MoveResizeRegionUseCase(service)

    project = Project("p1", "Test", "path", "sha", 100, 10, 1, datetime.now(UTC), datetime.now(UTC))

    old_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_bbox=Rect(0, 0, 10, 10),
        source_text="TEXT A",
        source_fragments=(),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    extractor.mock_result = TextExtractionResult(
        page_number=1,
        selection_rect=Rect(20, 20, 30, 30),
        source_bbox=Rect(20, 20, 30, 30),
        text="TEXT B",
        fragments=({"text": "TEXT B", "bbox": [20, 20, 30, 30]},),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        warnings=(),
    )

    new_region = use_case.execute(project, old_region, Rect(20, 20, 30, 30))

    assert new_region.id == old_region.id
    assert new_region.source_text == "TEXT B"
    assert new_region.selection_rect.x0 == 20
    assert new_region.created_at == old_region.created_at
    assert new_region.updated_at != old_region.updated_at


def test_no_native_text_cancels():
    extractor = MockExtractor()
    service = TextExtractionService(extractor)
    use_case = MoveResizeRegionUseCase(service)

    project = Project("p1", "Test", "path", "sha", 100, 10, 1, datetime.now(UTC), datetime.now(UTC))

    old_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_bbox=Rect(0, 0, 10, 10),
        source_text="TEXT A",
        source_fragments=({"text": "TEXT A", "bbox": [0, 0, 10, 10]},),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # Empty result automatically returned by MockExtractor when mock_result is None
    with pytest.raises(MoveResizeRegionError, match="No text found"):
        use_case.execute(project, old_region, Rect(50, 50, 60, 60))


def test_project_locked_raises_error():
    extractor = MockExtractor()
    service = TextExtractionService(extractor)
    use_case = MoveResizeRegionUseCase(service)

    project = Project("p1", "Test", "path", "sha", 100, 10, 1, datetime.now(UTC), datetime.now(UTC))

    old_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_bbox=Rect(0, 0, 10, 10),
        source_text="TEXT A",
        source_fragments=({"text": "TEXT A", "bbox": [0, 0, 10, 10]},),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(MoveResizeRegionError, match="Cannot edit regions in a locked project"):
        use_case.execute(project, old_region, Rect(20, 20, 30, 30), is_project_locked=True)


def test_move_resize_repository_failure_is_atomic():
    repo = MockRepo()
    old_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(0, 0, 1, 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.save(old_region)

    new_region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(1, 1, 2, 2),
        created_at=old_region.created_at,
        updated_at=datetime.now(UTC),
    )

    cmd = MoveResizeRegionCommand(old_region, new_region, repo)
    repo.should_fail = True
    from src.application.commands import CommandExecutionError

    with pytest.raises(CommandExecutionError):
        cmd.execute()

    # Verify repository was not updated with the new region
    assert repo.get("r1").selection_rect.x0 == 0
