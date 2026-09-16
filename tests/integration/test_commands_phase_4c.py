from datetime import UTC, datetime

from src.application.command_history import CommandHistory
from src.application.commands import (
    CreateRegionCommand,
    DeleteRegionCommand,
    MoveResizeRegionCommand,
)
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import ExtractionMethod
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository


def _create_region(id="r1", text="TEXT A", rect=None):
    rect = rect or Rect(0, 0, 10, 10)
    return TranslationRegion(
        id=id,
        project_id="p1",
        page_id=1,
        selection_rect=rect,
        source_bbox=rect,
        source_text=text,
        source_fragments=(),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


from src.infrastructure.persistence.database import Database


def _init_project(db: Database):
    with db.get_connection() as conn:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p1", "Test", "path", "sha", 100, 10, 1, now, now),
        )


def test_move_then_resize_history(tmp_path):
    db = Database(str(tmp_path / "test.sqlite"))
    db.init_schema()
    _init_project(db)
    repo = SqliteTranslationRegionRepository(db)
    history = CommandHistory()

    # Initial Create A
    reg_a = _create_region("r1", "TEXT A", Rect(0, 0, 10, 10))
    cmd_create = CreateRegionCommand(reg_a, repo)
    history.execute(cmd_create)

    # Move B
    reg_b = _create_region("r1", "TEXT B", Rect(10, 10, 20, 20))
    cmd_move = MoveResizeRegionCommand(reg_a, reg_b, repo)
    history.execute(cmd_move)

    # Resize C
    reg_c = _create_region("r1", "TEXT C", Rect(10, 10, 30, 30))
    cmd_resize = MoveResizeRegionCommand(reg_b, reg_c, repo)
    history.execute(cmd_resize)

    assert repo.get("r1").source_text == "TEXT C"

    # Undo B
    history.undo()
    assert repo.get("r1").source_text == "TEXT B"

    # Undo A
    history.undo()
    assert repo.get("r1").source_text == "TEXT A"

    # Redo B
    history.redo()
    assert repo.get("r1").source_text == "TEXT B"

    # Redo C
    history.redo()
    assert repo.get("r1").source_text == "TEXT C"


import pytest


def test_move_then_delete_undo(tmp_path):
    db = Database(str(tmp_path / "test.sqlite"))
    db.init_schema()
    _init_project(db)
    repo = SqliteTranslationRegionRepository(db)
    history = CommandHistory()

    reg_a = _create_region("r1", "TEXT A")
    history.execute(CreateRegionCommand(reg_a, repo))

    reg_b = _create_region("r1", "TEXT B", Rect(10, 10, 20, 20))
    history.execute(MoveResizeRegionCommand(reg_a, reg_b, repo))

    assert repo.get("r1").source_text == "TEXT B"

    history.execute(DeleteRegionCommand(reg_b.id, repo))
    assert repo.get("r1") is None

    history.undo()
    assert repo.get("r1").source_text == "TEXT B"


class FailingRepository(SqliteTranslationRegionRepository):
    def __init__(self, db, fail_on_save=False):
        super().__init__(db)
        self.fail_on_save = fail_on_save

    def save(self, region: TranslationRegion) -> None:
        if self.fail_on_save:
            raise RuntimeError("DB failed")
        super().save(region)


def test_undo_redo_retry_with_failing_repository(tmp_path):
    db = Database(str(tmp_path / "test.sqlite"))
    db.init_schema()
    _init_project(db)

    repo = FailingRepository(db)
    history = CommandHistory()

    reg_a = _create_region("r1", "TEXT A")
    history.execute(CreateRegionCommand(reg_a, repo))

    reg_b = _create_region("r1", "TEXT B", Rect(10, 10, 20, 20))
    history.execute(MoveResizeRegionCommand(reg_a, reg_b, repo))

    assert repo.get("r1").source_text == "TEXT B"
    assert history._current_index == 2

    # Simulate DB failure on undo
    repo.fail_on_save = True
    from src.application.commands import CommandExecutionError

    with pytest.raises(CommandExecutionError, match="DB failed"):
        history.undo()

    # Index should be unchanged, UI/CommandHistory state unchanged
    assert history._current_index == 2
    assert repo.get("r1").source_text == "TEXT B"

    # Retry success
    repo.fail_on_save = False
    history.undo()
    assert history._current_index == 1
    assert repo.get("r1").source_text == "TEXT A"


def test_persistence_roundtrip_after_move(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    db1 = Database(db_path)
    db1.init_schema()
    _init_project(db1)
    repo1 = SqliteTranslationRegionRepository(db1)

    reg_a = _create_region("r1", "TEXT A")
    repo1.save(reg_a)

    reg_b = _create_region("r1", "TEXT B", Rect(10, 10, 20, 20))
    repo1.save(reg_b)

    db2 = Database(db_path)
    repo2 = SqliteTranslationRegionRepository(db2)
    loaded = repo2.get("r1")

    assert loaded.source_text == "TEXT B"
    assert loaded.selection_rect == Rect(10, 10, 20, 20)
