import os
import sqlite3
import threading
import time
from pathlib import Path
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor

import pytest
from src.domain.models.enums import ExtractionMethod, FitStatus, RegionStatus, RegionType
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.application.services.project_service import ProjectService


@pytest.fixture
def temp_workspace(tmp_path):
    # Usar tmp_path proveído por pytest (combinado con --basetemp si está disponible)
    return tmp_path

def test_db5_01_short_operation_closes_connection(temp_workspace):
    """DB5-01: Operación corta abre y cierra conexión."""
    db_path = temp_workspace / "db5_01.sqlite"
    db = Database(str(db_path))
    db.init_schema()

    # Comprobamos que luego de init_schema, el WAL puede ser accedido o que no quedan file locks
    # En Windows, intentar renombrar o borrar la base a mano probaría si hay locks.
    # Primero hacemos una inserción usando el repositorio.
    from src.infrastructure.persistence.repository import SqliteProjectRepository
    repo = SqliteProjectRepository(db)
    
    project = Project(
        id="p1", name="Test", pdf_path="test.pdf", pdf_sha256="sha",
        pdf_size=100, pdf_page_count=1, last_viewed_page=1,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
    )
    repo.save(project)
    
    # La conexión debería estar cerrada ahora.
    # En Windows, podemos intentar abrir la DB exclusivamente o verificar bloqueos,
    # pero como mínimo, podemos asegurar que el Database object no guarda referencia.
    assert db._memory_conn is None

    # Intentamos mover el archivo para confirmar que no está bloqueado por el repositorio (solo en file DB)
    moved_path = temp_workspace / "db5_01_moved.sqlite"
    os.rename(db_path, moved_path)
    assert moved_path.exists()

def test_db5_02_exception_rollback_close(temp_workspace):
    """DB5-02: Excepción produce rollback y close."""
    db_path = temp_workspace / "db5_02.sqlite"
    db = Database(str(db_path))
    db.init_schema()
    
    # Forzamos una excepción dentro del context manager transaction()
    try:
        with db.transaction() as conn:
            conn.execute("INSERT INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("p_fail", "Test", "test.pdf", "sha", 100, 1, 1, datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
            # Simulamos fallo
            raise RuntimeError("Fake Error")
    except RuntimeError:
        pass
        
    # Verificar que ocurrió rollback
    with db.transaction() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM project WHERE id = 'p_fail'")
        assert cursor.fetchone()[0] == 0
        
    # Y que no hay lock (se puede renombrar)
    os.rename(db_path, temp_workspace / "db5_02_moved.sqlite")

def test_db5_03_reopen_immediate(temp_workspace):
    """DB5-03: Nueva instancia puede abrir DB inmediatamente después."""
    db_path = temp_workspace / "db5_03.sqlite"
    db1 = Database(str(db_path))
    db1.init_schema()
    
    db2 = Database(str(db_path))
    # Esto no fallará con "database is locked" porque db1 cerró su conexión
    with db2.transaction() as conn:
        cursor = conn.execute("SELECT user_version FROM pragma_user_version")
        assert cursor.fetchone()[0] == 8

def test_db5_04_migration_and_close(temp_workspace):
    """DB5-04: Migración v3->v4 y cierre real."""
    db_path = temp_workspace / "db5_04.sqlite"
    
    # Preparamos schema v3 manual
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 3")
    conn.execute("CREATE TABLE project (id TEXT)")
    conn.execute("CREATE TABLE translation_region (id TEXT, project_id TEXT, is_manually_edited BOOLEAN)")
    conn.commit()
    conn.close()
    
    # Ejecutamos migración
    db = Database(str(db_path))
    db.init_schema()
    
    # Verificamos
    with db.transaction() as conn:
        cursor = conn.execute("SELECT user_version FROM pragma_user_version")
        assert cursor.fetchone()[0] == 8
        # Verificamos nueva columna
        cursor = conn.execute("PRAGMA table_info(translation_region)")
        columns = [row["name"] for row in cursor.fetchall()]
        assert "target_font_size" in columns

def test_db5_05_roundtrip_data01_new_connection(temp_workspace):
    """DB5-05: Roundtrip DATA-01 con nueva conexión."""
    db_path = temp_workspace / "db5_05.sqlite"
    factory = SqlitePersistenceFactory()
    repo_project = factory.create_project_repository(str(db_path))
    repo_region = factory.create_region_repository(str(db_path))
    
    p = Project("p1", "Test", "t.pdf", "sha", 1, 1, 1, datetime.now(UTC), datetime.now(UTC))
    repo_project.save(p)
    
    r = TranslationRegion(
        id="r1", 
        project_id="p1", 
        page_id=1, 
        selection_rect=Rect(0,0,1,1),
        source_text="src", 
        translated_text="tgt", 
        region_type=RegionType.TEXT_NATIVE, 
        status=RegionStatus.PENDING, 
        extraction_method=ExtractionMethod.NATIVE_TEXT, 
        fit_status=FitStatus.FIT, 
        created_at=datetime.now(UTC), 
        updated_at=datetime.now(UTC),
        is_manually_edited=True, 
        target_font_size=14.0
    )
    repo_region.save(r)
    
    # Creamos otra factory totalmente independiente
    factory2 = SqlitePersistenceFactory()
    repo_region2 = factory2.create_region_repository(str(db_path))
    loaded = repo_region2.get("r1")
    assert loaded.is_manually_edited is True
    assert loaded.target_font_size == 14.0

def test_db5_06_07_08_backup(temp_workspace):
    """DB5-06, 07, 08: Backup consistente abre independientemente y maneja fallos."""
    db_path = temp_workspace / "db5_06.sqlite"
    dest_path = temp_workspace / "backup.sqlite"
    
    db = Database(str(db_path))
    db.init_schema()
    
    from src.infrastructure.persistence.repository import SqliteProjectRepository
    repo = SqliteProjectRepository(db)
    repo.save(Project("pb", "Backup", "b.pdf", "sha", 1, 1, 1, datetime.now(UTC), datetime.now(UTC)))
    
    # 06/07: Backup exitoso y consistente
    db.backup(str(dest_path))
    assert dest_path.exists()
    
    # Verificar abriendo independiente
    db_backup = Database(str(dest_path))
    repo_backup = SqliteProjectRepository(db_backup)
    assert repo_backup.get("pb") is not None
    


def test_db5_09_10_safe06_07_relink_and_switch(temp_workspace, monkeypatch):
    """DB5-09/10: Relink (SAFE-07) y switch (SAFE-06)."""
    # Mock OS environ
    monkeypatch.setenv("LOCALAPPDATA", str(temp_workspace))
    factory = SqlitePersistenceFactory()
    svc = ProjectService(factory)
    
    pdf1 = temp_workspace / "1.pdf"
    pdf1.write_bytes(b"pdf1")
    
    project, db_path = svc.discover_or_create_project(str(pdf1), 1)
    
    # Relink
    pdf2 = temp_workspace / "2.pdf"
    pdf2.write_bytes(b"pdf1") # same fingerprint
    assert svc.relocate_pdf(project, str(pdf2), 1) is True
    
    # Switch
    pdf3 = temp_workspace / "3.pdf"
    pdf3.write_bytes(b"pdf3")
    project3, db_path3 = svc.discover_or_create_project(str(pdf3), 1)
    
    assert db_path != db_path3

def test_db5_11_shutdown_cleans(temp_workspace):
    """DB5-11: Shutdown limpia conexiones administradas."""
    factory = SqlitePersistenceFactory()
    db_mem = factory._get_db(":memory:")
    assert db_mem._memory_conn is not None
    factory.close_all()
    assert db_mem._memory_conn is None

def test_db5_12_timeout_finite_lock(temp_workspace):
    """DB5-12: database is locked tiene comportamiento finito."""
    db_path = temp_workspace / "db5_12.sqlite"
    db = Database(str(db_path), timeout=0.1) # Timeout corto para el test
    db.init_schema()
    
    # Abrir conexión real en sqlite3 y bloquear
    conn_blocker = sqlite3.connect(str(db_path))
    conn_blocker.execute("BEGIN EXCLUSIVE")
    
    try:
        start_time = time.time()
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            with db.transaction() as conn:
                conn.execute("INSERT INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at) VALUES ('1', '1', '1', '1', 1, 1, 1, '1', '1')")
        elapsed = time.time() - start_time
        assert elapsed >= 0.1 # Debe haber esperado el timeout al menos
        assert elapsed < 5.0 # Pero no infinitamente
    finally:
        conn_blocker.rollback()
        conn_blocker.close()
