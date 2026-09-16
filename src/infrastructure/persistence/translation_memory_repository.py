import sqlite3
from typing import Sequence
from datetime import datetime
from src.domain.interfaces.translation_memory import ITranslationMemoryRepository
from src.domain.models.translation_memory import TranslationMemoryEntry
from src.infrastructure.persistence.database import Database

class SqliteTranslationMemoryRepository(ITranslationMemoryRepository):
    def __init__(self, db: Database):
        self.db = db

    def get_by_project_and_hash(self, project_id: str, target_language: str, source_hash: str) -> Sequence[TranslationMemoryEntry]:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM translation_memory_entry WHERE project_id = ? AND target_language = ? AND source_hash = ?",
                (project_id, target_language, source_hash)
            )
            rows = cursor.fetchall()
            return [self._map_row(row) for row in rows]

    def upsert(self, entry: TranslationMemoryEntry):
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO translation_memory_entry (
                    entry_id, project_id, source_text, source_normalized, source_hash,
                    target_text, target_language, region_id, block_id, translation_revision,
                    approved_at, glossary_id, glossary_revision, original_translation_engine,
                    original_translation_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
                ON CONFLICT(project_id, region_id, block_id) DO UPDATE SET 
                    source_text=excluded.source_text,
                    source_normalized=excluded.source_normalized,
                    source_hash=excluded.source_hash,
                    target_text=excluded.target_text,
                    target_language=excluded.target_language,
                    translation_revision=excluded.translation_revision,
                    approved_at=excluded.approved_at,
                    glossary_id=excluded.glossary_id,
                    glossary_revision=excluded.glossary_revision,
                    original_translation_engine=excluded.original_translation_engine,
                    original_translation_model=excluded.original_translation_model
                """,
                (
                    entry.entry_id, entry.project_id, entry.source_text, entry.source_normalized,
                    entry.source_hash, entry.target_text, entry.target_language, entry.region_id,
                    entry.block_id, entry.translation_revision, entry.approved_at.isoformat(),
                    entry.glossary_id, entry.glossary_revision, entry.original_translation_engine,
                    entry.original_translation_model
                )
            )

    def delete_for_region(self, region_id: str):
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM translation_memory_entry WHERE region_id = ?", (region_id,))

    def _map_row(self, row) -> TranslationMemoryEntry:
        return TranslationMemoryEntry(
            entry_id=row["entry_id"],
            project_id=row["project_id"],
            source_text=row["source_text"],
            source_normalized=row["source_normalized"],
            source_hash=row["source_hash"],
            target_text=row["target_text"],
            target_language=row["target_language"],
            region_id=row["region_id"],
            block_id=row["block_id"],
            translation_revision=row["translation_revision"],
            approved_at=datetime.fromisoformat(row["approved_at"]),
            glossary_id=row["glossary_id"],
            glossary_revision=row["glossary_revision"],
            original_translation_engine=row["original_translation_engine"],
            original_translation_model=row["original_translation_model"]
        )
