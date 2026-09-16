import sqlite3
from datetime import UTC, datetime

import pytest

from src.domain.models.enums import ExtractionMethod, FitStatus, RegionStatus, RegionType
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import (
    SqliteProjectRepository,
    SqliteTranslationRegionRepository,
)


@pytest.fixture
def memory_db():
    # Use memory database for testing with Database context manager
    with Database(":memory:") as db:
        db.init_schema()
        yield db


def test_database_initialization(memory_db):
    with memory_db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project'"
        )
        assert cursor.fetchone() is not None

        # Test schema version
        cursor = conn.execute("PRAGMA user_version")
        assert cursor.fetchone()[0] == 8


def test_database_schema_idempotence(memory_db):
    # Calling init_schema again should not fail
    memory_db.init_schema()
    with memory_db.get_connection() as conn:
        cursor = conn.execute("PRAGMA user_version")
        assert cursor.fetchone()[0] == 8


def test_project_upsert(memory_db):
    repo = SqliteProjectRepository(memory_db)
    now = datetime.now(UTC)
    proj = Project(
        id="proj_1",
        name="Test Book",
        pdf_path="/path",
        pdf_sha256="abc",
        pdf_size=1024,
        pdf_page_count=100,
        last_viewed_page=1,
        created_at=now,
        updated_at=now,
    )
    repo.save(proj)

    # Upsert (Modify)
    proj.name = "Modified Book"
    repo.save(proj)

    retrieved = repo.get("proj_1")
    assert retrieved.name == "Modified Book"

    # Ensure it didn't duplicate
    with memory_db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM project")
        assert cursor.fetchone()[0] == 1


def test_foreign_key_enforcement(memory_db):
    repo = SqliteTranslationRegionRepository(memory_db)
    region = TranslationRegion(
        id="reg_1",
        project_id="non_existent_project",
        page_id=1,
        selection_rect=Rect(0, 0, 100, 100),
    )

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repo.save(region)


def test_translation_region_round_trip(memory_db):
    # Create project first to satisfy FK
    proj_repo = SqliteProjectRepository(memory_db)
    now = datetime.now(UTC)
    proj = Project(
        id="proj_1",
        name="Test Book",
        pdf_path="/path",
        pdf_sha256="abc",
        pdf_size=1024,
        pdf_page_count=100,
        last_viewed_page=1,
        created_at=now,
        updated_at=now,
    )
    proj_repo.save(proj)

    repo = SqliteTranslationRegionRepository(memory_db)
    region = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(10, 20, 30, 40),
        source_bbox=None,  # Nullable test
        source_text="Hello",
        translated_text="Hola",
        region_type=RegionType.TEXT_NATIVE,
        status=RegionStatus.TRANSLATED,
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        fit_status=FitStatus.FIT,
    )
    repo.save(region)

    retrieved = repo.get("reg_1")
    assert retrieved is not None
    assert retrieved.selection_rect.x0 == 10
    assert retrieved.source_bbox is None
    assert retrieved.source_text == "Hello"
    assert retrieved.status == RegionStatus.TRANSLATED
    assert retrieved.is_manually_edited is False

    # Upsert with manual edit
    retrieved.change_status(RegionStatus.REVIEWED)
    retrieved.is_manually_edited = True
    repo.save(retrieved)

    retrieved_again = repo.get("reg_1")
    assert retrieved_again.status == RegionStatus.REVIEWED
    assert retrieved_again.is_manually_edited is True

    # get_by_page
    page_regions = repo.get_by_page("proj_1", 1)
    assert len(page_regions) == 1
    assert page_regions[0].id == "reg_1"
