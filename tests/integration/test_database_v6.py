import os
import sqlite3
import pytest
from src.infrastructure.persistence.database import Database


def test_v6_migration_creates_tables_and_columns(tmp_path):
    db_path = str(tmp_path / "test_v6.sqlite")
    
    # Create v5 schema
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE translation_region (id TEXT PRIMARY KEY, glossary_id TEXT, glossary_revision INTEGER, translation_revision INTEGER)")
        conn.execute("PRAGMA user_version = 5")
        
    db = Database(db_path)
    db.init_schema()
    
    # Verify v6 changes
    with db.transaction() as conn:
        cursor = conn.cursor()
        
        # Check active_glossary_id in project
        cursor.execute("PRAGMA table_info(project)")
        columns = [row["name"] for row in cursor.fetchall()]
        assert "active_glossary_id" in columns
        
        # Check glossary table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='glossary'")
        assert cursor.fetchone() is not None
        
        # Check glossary_entry table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='glossary_entry'")
        assert cursor.fetchone() is not None
        
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == 8


def test_v6_migration_idempotent(tmp_path):
    db_path = str(tmp_path / "test_v6_idempotent.sqlite")
    
    db = Database(db_path)
    db.init_schema()  # Migrates up to v6
    
    # Run again, shouldn't crash
    db.init_schema()
    
    with db.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == 8
