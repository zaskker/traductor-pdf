import sqlite3
import pytest
from src.infrastructure.persistence.database import Database
from src.domain.models.region import TranslationRegion
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository

def test_migration_v4_to_v5_adds_columns_and_preserves_data(tmp_path):
    db_path = tmp_path / "test.db"
    
    # 1. Simulate v4 schema
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Create tables exactly as in v4
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
            source_fragments TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            is_manually_edited BOOLEAN DEFAULT 0,
            translation_engine TEXT,
            translation_engine_version TEXT,
            target_font_size REAL,
            target_font_family TEXT,
            target_alignment TEXT,
            target_line_height REAL,
            fit_scale REAL,
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
        )
    """)
    
    # Insert v4 legacy data
    conn.execute(
        "INSERT INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at) "
        "VALUES ('proj-1', 'Test', 'test.pdf', 'abc', 100, 1, 0, '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO translation_region (id, project_id, page_id, selection_x0, selection_y0, selection_x1, selection_y1, "
        "source_text, translated_text, region_type, status, extraction_method, fit_status, translation_engine) "
        "VALUES ('reg-1', 'proj-1', 0, 0, 0, 100, 100, 'hello', 'hola', 'TEXT_NATIVE', 'TRANSLATED', 'NATIVE_TEXT', 'PENDING', 'ollama')"
    )
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()
    
    # 2. Open with our Database class (triggers init_schema -> migrates to v5)
    db = Database(str(db_path))
    db.init_schema()
    
    # 3. Verify columns exist
    with db.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(translation_region)")
        columns = {row["name"]: row["type"] for row in cursor.fetchall()}
        
        assert "translation_model" in columns
        assert "translated_blocks" in columns
        assert "prompt_template_version" in columns
        assert "translation_options" in columns
        assert "glossary_id" in columns
        assert "glossary_revision" in columns
        assert "translation_revision" in columns
        
    # 4. Read through repository to ensure it handles NULL legacy data without crashing
    repo = SqliteTranslationRegionRepository(db)
    region = repo.get("reg-1")
    assert region is not None
    assert region.translation_engine == "ollama"
    assert region.translated_blocks is None
    assert region.translation_model is None
    assert region.translation_options is None
    assert region.translation_revision is None
    assert region.glossary_id is None
    
    db.close()

def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.init_schema()
    
    # Second call should not crash
    db.init_schema()
    db.close()
