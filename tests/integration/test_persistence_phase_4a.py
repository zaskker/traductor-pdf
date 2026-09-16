import json
import sqlite3
import uuid
from datetime import UTC, datetime

from src.application.services.project_service import ProjectService
from src.domain.interfaces.persistence import IProjectRepository
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import FragmentGranularity, SourceFragment
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.infrastructure.persistence.repository import (
    SqliteProjectRepository,
    SqliteTranslationRegionRepository,
)


def test_schema_migration_v1_to_v2(tmp_path):
    db_path = str(tmp_path / "migration.sqlite")
    # Simulate an old v1 database manually
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("""
        CREATE TABLE project (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            pdf_sha256 TEXT NOT NULL,
            pdf_size INTEGER NOT NULL,
            pdf_page_count INTEGER NOT NULL,
            last_viewed_page INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE translation_region (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id INTEGER NOT NULL,
            selection_x0 REAL NOT NULL,
            selection_y0 REAL NOT NULL,
            selection_x1 REAL NOT NULL,
            selection_y1 REAL NOT NULL,
            source_bbox_x0 REAL,
            source_bbox_y0 REAL,
            source_bbox_x1 REAL,
            source_bbox_y1 REAL,
            source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            region_type TEXT NOT NULL,
            status TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            fit_status TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
        )
    """)

    # Insert v1 data
    conn.execute("""
        INSERT INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at)
        VALUES ('proj_1', 'Test', '/path', 'sha', 100, 10, 1, '2026-01-01T00:00:00', '2026-01-01T00:00:00')
    """)
    conn.execute("""
        INSERT INTO translation_region (id, project_id, page_id, selection_x0, selection_y0, selection_x1, selection_y1, source_text, translated_text, region_type, status, extraction_method, fit_status)
        VALUES ('reg_1', 'proj_1', 1, 0, 0, 10, 10, 'Hello', '', 'TEXT_NATIVE', 'PENDING', 'NATIVE_TEXT', 'PENDING')
    """)
    conn.commit()
    conn.close()

    # Now open with our Database class which should trigger migration
    with Database(db_path) as db:
        db.init_schema()
        with db.get_connection() as c:
            cursor = c.execute("PRAGMA user_version")
            assert cursor.fetchone()[0] == 8

            # Check if columns exist and default values are set
            cursor = c.execute(
                "SELECT source_fragments, created_at, updated_at FROM translation_region WHERE id = 'reg_1'"
            )
            row = cursor.fetchone()
            assert row is not None
            fragments_json, created_at, updated_at = row

            data = json.loads(fragments_json)
            assert data["version"] == 1
            assert data["fragments"] == []

            assert created_at is not None
            assert updated_at is not None


def test_region_roundtrip_with_fragments(tmp_path):
    db_path = tmp_path / "test.sqlite"
    with Database(str(db_path)) as db:
        db.init_schema()
        proj_repo = SqliteProjectRepository(db)
        reg_repo = SqliteTranslationRegionRepository(db)

        proj_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        proj = Project(proj_id, "Test", "/path", "sha", 100, 10, 1, now, now)
        proj_repo.save(proj)

        frag = SourceFragment(
            text="Hello",
            bbox=Rect(0, 0, 10, 10),
            granularity=FragmentGranularity.WORD,
            block_index=0,
            line_index=0,
            span_index=0,
            raw_font_name="Arial",
            font_size=12.0,
            font_color="#000000",
            font_flags_raw=0,
            is_bold=False,
            is_italic=False,
            is_serif=False,
            is_monospace=False,
        )

        reg_id = str(uuid.uuid4())
        region = TranslationRegion(
            id=reg_id,
            project_id=proj_id,
            page_id=2,  # 1-based UI numbering
            selection_rect=Rect(0, 0, 10, 10),
            source_fragments=[frag],
            source_text="Hello",
            created_at=now,
            updated_at=now,
        )

        reg_repo.save(region)

        # Roundtrip
        retrieved = reg_repo.get(reg_id)
        assert retrieved.page_id == 2  # verify page numbering persisted
        assert len(retrieved.source_fragments) == 1
        r_frag = retrieved.source_fragments[0]
        assert r_frag.text == "Hello"
        assert r_frag.bbox.x1 == 10
        assert r_frag.raw_font_name == "Arial"
        assert r_frag.is_bold is False


def test_get_by_page(tmp_path):
    db_path = tmp_path / "test2.sqlite"
    with Database(str(db_path)) as db:
        db.init_schema()
        proj_repo = SqliteProjectRepository(db)
        reg_repo = SqliteTranslationRegionRepository(db)

        proj_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        proj = Project(proj_id, "Test", "/path", "sha", 100, 10, 1, now, now)
        proj_repo.save(proj)

        # Insert 3 regions on page 1, 2 on page 2
        for i in range(3):
            reg = TranslationRegion(
                str(uuid.uuid4()), proj_id, 1, Rect(0, 0, 1, 1), created_at=now, updated_at=now
            )
            reg_repo.save(reg)

        for i in range(2):
            reg = TranslationRegion(
                str(uuid.uuid4()), proj_id, 2, Rect(0, 0, 1, 1), created_at=now, updated_at=now
            )
            reg_repo.save(reg)

        assert len(reg_repo.get_by_page(proj_id, 1)) == 3
        assert len(reg_repo.get_by_page(proj_id, 2)) == 2
        assert len(reg_repo.get_by_page(proj_id, 3)) == 0


def test_project_service_fingerprint_logic(tmp_path):
    class FakeRepo(IProjectRepository):
        def save(self, project):
            pass

        def get(self, project_id):
            return None

    svc = ProjectService(SqlitePersistenceFactory())

    # Create fake PDF
    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"dummy content")

    # Check fingerprint creation
    sha, size = svc._compute_fingerprint(str(pdf_path))
    assert size == 13
    assert sha is not None

    proj = Project(
        "id", "Test", str(pdf_path), sha, size, 1, 1, datetime.now(UTC), datetime.now(UTC)
    )

    # Fingerprint matching logic
    assert svc.check_project_locked(proj, str(pdf_path), 1) is False

    # Change page count
    assert svc.check_project_locked(proj, str(pdf_path), 2) is True

    # Change file bytes
    pdf_path.write_bytes(b"different content")  # size 17
    assert svc.check_project_locked(proj, str(pdf_path), 1) is True

    # Same size, different bytes
    pdf_path.write_bytes(b"dummy context")  # size 13
    assert svc.check_project_locked(proj, str(pdf_path), 1) is True

    # Relocation
    pdf_path2 = tmp_path / "relocated.pdf"
    pdf_path2.write_bytes(b"dummy content")

    # Should be locked since pdf_path points to dummy context which has mismatch
    assert svc.relocate_pdf(proj, str(pdf_path2), 1) is True
    assert proj.pdf_path == str(pdf_path2)


def test_restart_recovery(tmp_path):
    class FakeRepo(IProjectRepository):
        def save(self, project):
            pass

        def get(self, project_id):
            return None

    svc = ProjectService(SqlitePersistenceFactory())
    # override base_dir to tmp_path for test
    svc.base_dir = tmp_path

    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"dummy content")

    # Session 1: Create project and save region
    proj, db_path = svc.discover_or_create_project(str(pdf_path), 1)
    svc.bind_to_project_db(db_path)
    # Save project to repo
    svc._project_repo.save(proj)

    reg_id = str(uuid.uuid4())
    region = TranslationRegion(
        id=reg_id,
        project_id=proj.id,
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Text",
    )
    svc.region_repo.save(region)

    # Close DB (simulate restart)
    svc._persistence_factory.close_all()

    # Session 2: Reopen project
    svc2 = ProjectService(SqlitePersistenceFactory())
    svc2.base_dir = tmp_path
    proj2, db_path2 = svc2.discover_or_create_project(str(pdf_path), 1)

    assert proj2.id == proj.id

    svc2.bind_to_project_db(db_path2)
    regions = svc2.region_repo.get_by_page(proj2.id, 1)
    assert len(regions) == 1
    assert regions[0].id == reg_id
    assert regions[0].source_text == "Text"
    svc2._persistence_factory.close_all()
