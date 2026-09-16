from datetime import UTC, datetime

from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository


def test_sqlite_migration_v2_to_v3():
    # Arrange: Create a database and mock it up to v2 manually
    db = Database(":memory:")
    with db.get_connection() as conn:
        db._migrate_to_v1(conn)
        conn.execute("PRAGMA user_version = 1")
        db._migrate_to_v2(conn)
        conn.execute("PRAGMA user_version = 2")

        # Insert a region in v2 schema (no is_manually_edited column)
        now_str = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at)
            VALUES ('proj_old', 'Old Project', '/path', 'hash', 100, 10, 1, ?, ?)
            """,
            (now_str, now_str),
        )
        conn.execute(
            """
            INSERT INTO translation_region 
            (id, project_id, page_id, selection_x0, selection_y0, selection_x1, selection_y1,
             source_text, translated_text, region_type, status, extraction_method, fit_status)
            VALUES ('reg_old', 'proj_old', 1, 0, 0, 10, 10, 'Hello', 'Hola', 'TEXT_NATIVE', 'TRANSLATED', 'NATIVE_TEXT', 'FIT')
            """
        )
        conn.commit()

    # Act: Trigger init_schema to run migration v3
    db.init_schema()

    # Assert: Verify column was added and default value is False
    with db.get_connection() as conn:
        cursor = conn.execute("PRAGMA user_version")
        assert cursor.fetchone()[0] == 8

    repo = SqliteTranslationRegionRepository(db)
    retrieved = repo.get("reg_old")
    assert retrieved is not None
    assert retrieved.is_manually_edited is False
