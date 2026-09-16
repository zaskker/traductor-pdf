import contextlib
import os
import sqlite3
import tempfile
from datetime import UTC
from pathlib import Path


class Database:
    def __init__(self, db_path: str, timeout: float = 5.0):
        self.db_path = db_path
        self.timeout = timeout
        self._memory_conn: sqlite3.Connection | None = None
        import threading
        self._local = threading.local()
        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._setup_connection(self._memory_conn)

    def _setup_connection(self, conn: sqlite3.Connection):
        # Activar WAL mode para mayor concurrencia y seguridad en transacciones
        conn.execute("PRAGMA journal_mode=WAL")
        # Activar Foreign Keys explícitamente en la conexión
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row

    def get_connection(self) -> sqlite3.Connection:
        if self._memory_conn:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        self._setup_connection(conn)
        return conn

    @contextlib.contextmanager
    def transaction(self):
        """
        Orquesta una Operación Corta:
        1. Crea conexión.
        2. Envuelve en transacción (commit/rollback automático con 'with conn').
        3. Cierra la conexión explícitamente en finally (salvo :memory:).
        """
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            yield self._local.conn
            return
        conn = self.get_connection()
        self._local.conn = conn
        try:
            with conn:
                yield conn
        finally:
            self._local.conn = None
            if conn != self._memory_conn:
                conn.close()

    def close(self):
        """Cierra explícitamente la conexión si es en memoria."""
        if self._memory_conn:
            self._memory_conn.close()
            self._memory_conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def backup(self, dest_path: str):
        """
        Realiza un backup consistente a dest_path utilizando la API de backup de SQLite.
        Utiliza un archivo temporal en el mismo directorio para lograr reemplazo atómico.
        """
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Usar un archivo temporal en el mismo directorio para asegurar rename atómico
        temp_fd, temp_path = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".tmp")
        os.close(temp_fd)
        
        temp_file = Path(temp_path)
        try:
            with self.transaction() as source_conn:
                # Abrir conexión destino
                dest_conn = sqlite3.connect(str(temp_file))
                try:
                    # Ejecutar backup
                    source_conn.backup(dest_conn)
                    
                    # Validar backup
                    source_cursor = source_conn.cursor()
                    source_cursor.execute("PRAGMA user_version")
                    source_version = source_cursor.fetchone()[0]

                    dest_cursor = dest_conn.cursor()
                    dest_cursor.execute("PRAGMA user_version")
                    dest_version = dest_cursor.fetchone()[0]

                    if source_version != dest_version:
                        raise RuntimeError(f"Backup user_version mismatch: source={source_version}, dest={dest_version}")

                    dest_cursor.execute("PRAGMA integrity_check")
                    res = dest_cursor.fetchone()
                    if res[0] != "ok":
                        raise RuntimeError(f"Backup integrity check failed: {res[0]}")
                        
                finally:
                    dest_conn.close()
            
            os.replace(temp_file, dest)
                
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    def init_schema(self):
        """Inicializa o migra el esquema de la base de datos."""
        with self.transaction() as conn:
            # Force transaction start for DDL statements
            conn.execute("BEGIN")
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]

            if version < 1:
                self._migrate_to_v1(conn)
                conn.execute("PRAGMA user_version = 1")
                version = 1

            if version < 2:
                self._migrate_to_v2(conn)
                conn.execute("PRAGMA user_version = 2")
                version = 2

            if version < 3:
                self._migrate_to_v3(conn)
                conn.execute("PRAGMA user_version = 3")
                version = 3

            if version < 4:
                self._migrate_to_v4(conn)
                conn.execute("PRAGMA user_version = 4")
                version = 4

            if version < 5:
                self._migrate_to_v5(conn)
                conn.execute("PRAGMA user_version = 5")
                version = 5

            if version < 6:
                self._migrate_to_v6(conn)
                conn.execute("PRAGMA user_version = 6")
                version = 6

            if version < 7:
                self._migrate_to_v7(conn)
                conn.execute("PRAGMA user_version = 7")
                version = 7

            if version < 8:
                self._migrate_to_v8(conn)
                conn.execute("PRAGMA user_version = 8")
                version = 8
    
            # After migrations, ensure FK is ON (needed for SQLite)
            conn.execute("PRAGMA foreign_keys = ON")

    def _migrate_to_v1(self, conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project (
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
        # TranslationRegion minimal schema for Phase 0
        conn.execute("""
            CREATE TABLE IF NOT EXISTS translation_region (
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

    def _migrate_to_v2(self, conn: sqlite3.Connection):
        import json
        from datetime import datetime

        conn.execute("ALTER TABLE translation_region ADD COLUMN source_fragments TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN created_at TIMESTAMP")
        conn.execute("ALTER TABLE translation_region ADD COLUMN updated_at TIMESTAMP")

        empty_fragments = json.dumps({"version": 1, "fragments": []})
        now_iso = datetime.now(UTC).isoformat()

        conn.execute(
            "UPDATE translation_region SET source_fragments = ?, created_at = ?, updated_at = ?",
            (empty_fragments, now_iso, now_iso),
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_translation_region_project_page ON translation_region(project_id, page_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_translation_region_project ON translation_region(project_id)"
        )

    def _migrate_to_v3(self, conn: sqlite3.Connection):
        conn.execute(
            "ALTER TABLE translation_region ADD COLUMN is_manually_edited BOOLEAN DEFAULT 0"
        )

    def _migrate_to_v4(self, conn: sqlite3.Connection):
        conn.execute("ALTER TABLE translation_region ADD COLUMN translation_engine TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN translation_engine_version TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN target_font_size REAL")
        conn.execute("ALTER TABLE translation_region ADD COLUMN target_font_family TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN target_alignment TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN target_line_height REAL")
        conn.execute("ALTER TABLE translation_region ADD COLUMN fit_scale REAL")

    def _migrate_to_v5(self, conn: sqlite3.Connection):
        conn.execute("ALTER TABLE translation_region ADD COLUMN translation_model TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN translated_blocks TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN prompt_template_version TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN translation_options TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN glossary_id TEXT")
        conn.execute("ALTER TABLE translation_region ADD COLUMN glossary_revision INTEGER")
        conn.execute("ALTER TABLE translation_region ADD COLUMN translation_revision INTEGER")

    def _migrate_to_v6(self, conn: sqlite3.Connection):
        # Add active_glossary_id to project
        conn.execute("ALTER TABLE project ADD COLUMN active_glossary_id TEXT")
        
        # Create glossary and glossary_entry tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS glossary (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                revision INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS glossary_entry (
                id TEXT PRIMARY KEY,
                glossary_id TEXT NOT NULL,
                source_term TEXT NOT NULL,
                target_term TEXT NOT NULL,
                FOREIGN KEY(glossary_id) REFERENCES glossary(id) ON DELETE CASCADE
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_glossary_project ON glossary(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_glossary_entry_glossary ON glossary_entry(glossary_id)")

    def _migrate_to_v7(self, conn: sqlite3.Connection):
        """TRANS-05: Add review/approval revision tracking columns.

        These columns are nullable — existing translations start as UNREVIEWED (NULL),
        which is the correct interpretation: we do not invent that they were reviewed.
        Migration is idempotent: each ALTER is wrapped individually so if a column
        already exists (e.g. re-running on a partial migration), it is skipped.
        """
        columns_to_add = [
            ("reviewed_translation_revision", "INTEGER"),
            ("approved_translation_revision", "INTEGER"),
            ("reviewed_at", "TIMESTAMP"),
            ("approved_at", "TIMESTAMP"),
        ]
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(
                    f"ALTER TABLE translation_region ADD COLUMN {col_name} {col_type}"
                )
            except Exception:
                # Column already exists — idempotent
                pass

    def _migrate_to_v8(self, conn: sqlite3.Connection):
        """TRANS-06: Add bilingual corpus / translation memory.
        
        Creates the translation_memory_entry table to store approved block-level translations.
        Includes a UNIQUE constraint on provenance (project_id, region_id, block_id).
        Includes ON DELETE CASCADE for project deletion.
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS translation_memory_entry (
                entry_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_text TEXT NOT NULL,
                source_normalized TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                target_text TEXT NOT NULL,
                target_language TEXT NOT NULL,
                region_id TEXT NOT NULL,
                block_id TEXT NOT NULL,
                translation_revision INTEGER NOT NULL,
                approved_at TIMESTAMP NOT NULL,
                glossary_id TEXT,
                glossary_revision INTEGER,
                original_translation_engine TEXT,
                original_translation_model TEXT,
                UNIQUE(project_id, region_id, block_id),
                FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_translation_memory_project_lang_hash ON translation_memory_entry(project_id, target_language, source_hash)")
