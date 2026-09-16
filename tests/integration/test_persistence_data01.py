import os
import sqlite3
from datetime import datetime, UTC
import pytest
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteProjectRepository, SqliteTranslationRegionRepository
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.domain.models.enums import ExtractionMethod, FitStatus, RegionStatus, RegionType

# --- HELPERS ---
def create_legacy_v3_db(db_path: str):
    """Creates a DB matching the exact state of schema version 3."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 3")
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
            FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
        )
    """)
    # Insert legacy project
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO project VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("proj-1", "Legacy Project", "/path/to/legacy.pdf", "sha", 1024, 5, 1, now, now)
    )
    # Insert legacy region
    conn.execute(
        """INSERT INTO translation_region 
        (id, project_id, page_id, selection_x0, selection_y0, selection_x1, selection_y1,
         source_text, translated_text, region_type, status, extraction_method, fit_status, is_manually_edited)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("reg-1", "proj-1", 1, 10.0, 10.0, 100.0, 100.0,
         "Hello", "Hola", "TEXT_NATIVE", "TRANSLATED", "NATIVE_TEXT", "PENDING", 0)
    )
    conn.commit()
    conn.close()

# --- D1: Nueva DB -> schema actual ---
def test_d1_new_db_schema_actual(tmp_path):
    db_path = str(tmp_path / "d1.db")
    db = Database(db_path)
    db.init_schema()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 8
    
    cursor.execute("PRAGMA table_info(translation_region)")
    columns = [row["name"] for row in cursor.fetchall()]
    assert "target_font_size" in columns
    assert "translation_engine" in columns
    
    db.close()

# --- D2: DB anterior -> migración exitosa ---
def test_d2_legacy_db_migration(tmp_path):
    db_path = str(tmp_path / "d2.db")
    create_legacy_v3_db(db_path)
    
    db = Database(db_path)
    db.init_schema()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 8
    
    cursor.execute("SELECT * FROM translation_region WHERE id='reg-1'")
    row = dict(cursor.fetchone())
    assert row["source_text"] == "Hello"
    assert row["target_font_size"] is None
    assert row["translation_engine"] is None
    db.close()

# --- D3: Migración repetida -> idempotente ---
def test_d3_idempotent_migration(tmp_path):
    db_path = str(tmp_path / "d3.db")
    create_legacy_v3_db(db_path)
    
    # First open
    db1 = Database(db_path)
    db1.init_schema()
    db1.close()
    
    # Second open
    db2 = Database(db_path)
    db2.init_schema()
    conn = db2.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 8
    db2.close()

# --- D4 & D5 & D6 & D7: Roundtrip exacto de región y campos persistidos ---
def test_d4_d5_d6_d7_exact_roundtrip(tmp_path):
    db_path = str(tmp_path / "d4.db")
    db = Database(db_path)
    db.init_schema()
    
    p_repo = SqliteProjectRepository(db)
    r_repo = SqliteTranslationRegionRepository(db)
    
    project = Project(
        id="p1",
        name="Test",
        pdf_path="/path/test.pdf",
        pdf_sha256="abc",
        pdf_size=100,
        pdf_page_count=1,
        last_viewed_page=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    p_repo.save(project)
    
    region = TranslationRegion(
        id="r1",
        project_id="p1",
        page_id=1,
        selection_rect=Rect(10, 20, 30, 40),
        source_bbox=Rect(11, 21, 29, 39),
        source_text="Test source",
        translated_text="Test target (edited)",
        is_manually_edited=True,
        region_type=RegionType.TEXT_NATIVE,
        status=RegionStatus.TRANSLATED,
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        fit_status=FitStatus.FIT,
        target_font_size=12.5,
        target_font_family="Helvetica",
        target_alignment="center",
        target_line_height=1.2,
        translation_engine="ollama",
        translation_engine_version="llama3",
        fit_scale=0.9,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    r_repo.save(region)
    db.close()
    
    # Reopen
    db2 = Database(db_path)
    r_repo2 = SqliteTranslationRegionRepository(db2)
    loaded = r_repo2.get("r1")
    
    assert loaded is not None
    assert loaded.id == region.id
    assert loaded.selection_rect == region.selection_rect
    assert loaded.source_bbox == region.source_bbox
    assert loaded.source_text == "Test source"
    assert loaded.translated_text == "Test target (edited)"
    assert loaded.is_manually_edited is True
    assert loaded.target_font_size == 12.5
    assert loaded.target_font_family == "Helvetica"
    assert loaded.target_alignment == "center"
    assert loaded.target_line_height == 1.2
    assert loaded.translation_engine == "ollama"
    assert loaded.translation_engine_version == "llama3"
    assert loaded.fit_scale == 0.9
    
    db2.close()

# --- D11: Geometría persiste sin desplazamiento ---
def test_d11_geometry_precision(tmp_path):
    db_path = str(tmp_path / "d11.db")
    db = Database(db_path)
    db.init_schema()
    
    p_repo = SqliteProjectRepository(db)
    r_repo = SqliteTranslationRegionRepository(db)
    
    project = Project("p1", "Test", "/a", "sha", 1, 1, 1, datetime.now(UTC), datetime.now(UTC))
    p_repo.save(project)
    
    # Use exact floats with high precision
    rect = Rect(10.1234567, 20.9876543, 30.1111111, 40.2222222)
    region = TranslationRegion(
        id="r1", project_id="p1", page_id=1, selection_rect=rect
    )
    r_repo.save(region)
    db.close()
    
    db2 = Database(db_path)
    loaded = SqliteTranslationRegionRepository(db2).get("r1")
    
    # Compare with high tolerance or exact depending on sqlite float storage
    # SQLite REAL stores IEEE 754 64-bit floats, which should be exact for these values
    assert loaded.selection_rect.x0 == rect.x0
    assert loaded.selection_rect.y0 == rect.y0
    assert loaded.selection_rect.x1 == rect.x1
    assert loaded.selection_rect.y1 == rect.y1
    
    db2.close()

# --- D12: Fallo de migración no destruye base ---
def test_d12_migration_failure(tmp_path):
    db_path = str(tmp_path / "d12.db")
    create_legacy_v3_db(db_path)
    
    # We simulate a failure by breaking the _migrate_to_v4 method in Database
    class BrokenDatabase(Database):
        def _migrate_to_v4(self, conn: sqlite3.Connection):
            conn.execute("ALTER TABLE translation_region ADD COLUMN translation_engine TEXT")
            # Sabotage the migration!
            conn.execute("ALTER TABLE table_that_does_not_exist ADD COLUMN foo TEXT")
            
    db = BrokenDatabase(db_path)
    with pytest.raises(sqlite3.OperationalError):
        db.init_schema()
        
    # Check that it did NOT advance to version 4, and the table was NOT modified (rolled back)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 3
    
    # translation_engine should NOT exist because the transaction rolled back
    cursor.execute("PRAGMA table_info(translation_region)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "translation_engine" not in columns
    
    conn.close()
