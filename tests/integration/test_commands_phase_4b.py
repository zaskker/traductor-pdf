import uuid
from datetime import UTC, datetime

import pytest

from src.application.commands import CommandExecutionError, CreateRegionCommand, DeleteRegionCommand
from src.domain.interfaces.persistence import ITranslationRegionRepository
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import (
    SqliteProjectRepository,
    SqliteTranslationRegionRepository,
)


def test_create_command_execute_undo_redo(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    with Database(db_path) as db:
        db.init_schema()
        proj_repo = SqliteProjectRepository(db)
        repo = SqliteTranslationRegionRepository(db)

        proj_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        proj_repo.save(Project(proj_id, "Test", "/path", "sha", 100, 10, 1, now, now))

        reg_id = str(uuid.uuid4())
        region = TranslationRegion(
            reg_id, proj_id, 1, Rect(0, 0, 1, 1), created_at=now, updated_at=now
        )

        cmd = CreateRegionCommand(region, repo)

        # Execute
        cmd.execute()
        assert repo.get(reg_id) is not None

        # Undo
        cmd.undo()
        assert repo.get(reg_id) is None

        # Redo
        cmd.redo()
        assert repo.get(reg_id) is not None


def test_delete_command_execute_undo_redo(tmp_path):
    db_path = str(tmp_path / "test2.sqlite")
    with Database(db_path) as db:
        db.init_schema()
        proj_repo = SqliteProjectRepository(db)
        repo = SqliteTranslationRegionRepository(db)

        proj_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        proj_repo.save(Project(proj_id, "Test", "/path", "sha", 100, 10, 1, now, now))

        reg_id = str(uuid.uuid4())
        region = TranslationRegion(
            reg_id, proj_id, 1, Rect(0, 0, 1, 1), created_at=now, updated_at=now
        )
        repo.save(region)

        cmd = DeleteRegionCommand(reg_id, repo)

        # Execute
        cmd.execute()
        assert repo.get(reg_id) is None

        # Undo
        cmd.undo()
        assert repo.get(reg_id) is not None

        # Redo
        cmd.redo()
        assert repo.get(reg_id) is None


def test_command_db_failure_rollback():
    class FailingRepo(ITranslationRegionRepository):
        def save(self, region):
            raise sqlite3.OperationalError("DB Locked")

        def get(self, region_id):
            return None

        def delete(self, region_id):
            pass

        def get_by_page(self, project_id, page_id):
            return []

        def get_all(self, project_id):
            return []

        def count(self, project_id):
            return 0

    repo = FailingRepo()
    region = TranslationRegion("r1", "p1", 1, Rect(0, 0, 1, 1))

    cmd = CreateRegionCommand(region, repo)
    import sqlite3

    with pytest.raises(CommandExecutionError):
        cmd.execute()

    # Command didn't execute successfully, so undo should do nothing (not crash)
    cmd.undo()
