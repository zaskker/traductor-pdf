from src.application.services.project_service import ProjectService
from src.infrastructure.persistence.factory import SqlitePersistenceFactory


def test_project_persisted_immediately(tmp_path):
    svc = ProjectService(SqlitePersistenceFactory())
    svc.base_dir = tmp_path
    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"dummy pdf content")

    # DO NOT navigate, DO NOT call update_last_viewed_page
    proj, db_path = svc.discover_or_create_project(str(pdf_path), 1)

    # Inmediatamente abrimos directo mediante un repo nuevo, sin pasar por el lifecycle usual de UI
    factory = SqlitePersistenceFactory()
    repo = factory.create_project_repository(db_path)
    persisted = repo.get(proj.id)

    assert persisted is not None
    assert persisted.id == proj.id
    assert persisted.pdf_sha256 == proj.pdf_sha256
    assert persisted.last_viewed_page == 1
    factory.close_all()


def test_discovery_after_restart_returns_same_uuid(tmp_path):
    svc = ProjectService(SqlitePersistenceFactory())
    svc.base_dir = tmp_path
    pdf_path = tmp_path / "dummy2.pdf"
    pdf_path.write_bytes(b"another dummy content")

    # First open
    proj1, db_path1 = svc.discover_or_create_project(str(pdf_path), 5)

    # Destruir servicio y simular restart cerrando BD
    svc._persistence_factory.close_all()
    del svc

    # Second open
    svc2 = ProjectService(SqlitePersistenceFactory())
    svc2.base_dir = tmp_path
    proj2, db_path2 = svc2.discover_or_create_project(str(pdf_path), 5)

    assert proj2.id == proj1.id
    assert db_path2 == db_path1
    svc2._persistence_factory.close_all()


def test_discovery_directory_count(tmp_path):
    svc = ProjectService(SqlitePersistenceFactory())
    svc.base_dir = tmp_path
    pdf_path = tmp_path / "dummy3.pdf"
    pdf_path.write_bytes(b"yet another dummy")

    svc.discover_or_create_project(str(pdf_path), 10)

    # Contar directorios
    dirs_before = [d for d in tmp_path.iterdir() if d.is_dir()]
    assert len(dirs_before) == 1

    svc._persistence_factory.close_all()

    svc2 = ProjectService(SqlitePersistenceFactory())
    svc2.base_dir = tmp_path
    svc2.discover_or_create_project(str(pdf_path), 10)

    dirs_after = [d for d in tmp_path.iterdir() if d.is_dir()]
    assert len(dirs_after) == 1
    svc2._persistence_factory.close_all()
