import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from src.domain.interfaces.persistence import (
    IProjectPersistenceFactory,
    IProjectRepository,
    ITranslationRegionRepository,
)
from src.domain.models.project import Project


class ProjectLockedError(Exception):
    pass


class ProjectService:
    def __init__(self, persistence_factory: IProjectPersistenceFactory):
        self._persistence_factory = persistence_factory
        self._project_repo: IProjectRepository | None = None
        self.region_repo: ITranslationRegionRepository | None = None
        self.glossary_repo = None # Actually, IGlossaryRepository | None = None
        self.uow = None # Actually, IUnitOfWork | None = None
        self.db_path: str | None = None

        # Local app data directory
        from src.application.runtime import get_app_data_path
        self.base_dir = get_app_data_path() / "projects"

        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _compute_fingerprint(self, pdf_path: str) -> tuple[str, int]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

        size = path.stat().st_size

        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest(), size

    def discover_or_create_project(self, pdf_path: str, page_count: int) -> tuple[Project, str]:
        """
        Descubre un proyecto existente comparando el fingerprint.
        Retorna (Project, db_path).
        """
        sha256, size = self._compute_fingerprint(pdf_path)

        # Enumerate projects
        match_project_id = None
        for project_dir in self.base_dir.iterdir():
            if project_dir.is_dir():
                db_path = project_dir / "project.sqlite"
                if db_path.exists():
                    try:
                        repo = self._persistence_factory.create_project_repository(str(db_path))
                        project = repo.get(project_dir.name)
                        if project:  # noqa: SIM102
                            if (
                                project.pdf_sha256 == sha256
                                and project.pdf_size == size
                                and project.pdf_page_count == page_count
                            ):
                                match_project_id = project_dir.name
                                break
                    except Exception:  # noqa: BLE001, S110
                        pass  # Ignore corrupted projects during discovery

        if match_project_id:
            # Re-read matched project formally (assuming caller will use it)
            db_path = str(self.base_dir / match_project_id / "project.sqlite")
            self.bind_to_project_db(db_path)
            project = self.open_project(match_project_id)
            if project.pdf_path != pdf_path:
                self.relocate_pdf(project, pdf_path, page_count)
            return project, db_path

        # Create new project
        new_id = str(uuid.uuid4())
        project_dir = self.base_dir / new_id
        project_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(project_dir / "project.sqlite")

        now = datetime.now(UTC)
        project = Project(
            id=new_id,
            name=f"{Path(pdf_path).name} Translation",
            pdf_path=pdf_path,
            pdf_sha256=sha256,
            pdf_size=size,
            pdf_page_count=page_count,
            last_viewed_page=1,  # 1-based page numbering
            created_at=now,
            updated_at=now,
        )

        self.bind_to_project_db(db_path)
        self._project_repo.save(project)

        return project, db_path

    def open_project(self, project_id: str) -> Project:
        if not self._project_repo:
            raise ValueError("Project repo not bound")
        project = self._project_repo.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        return project

    def update_last_viewed_page(self, project: Project, page_number: int):
        project.last_viewed_page = page_number
        project.updated_at = datetime.now(UTC)
        self._project_repo.save(project)

    def check_project_locked(self, project: Project, pdf_path: str, page_count: int) -> bool:
        """
        Retorna True si el proyecto está LOCKED (fingerprint mismatch).
        Retorna False si el fingerprint coincide.
        """
        try:
            sha256, size = self._compute_fingerprint(pdf_path)
        except FileNotFoundError:
            return True  # PDF no existe, proyecto bloqueado hasta relocation

        return (
            project.pdf_sha256 != sha256
            or project.pdf_size != size
            or project.pdf_page_count != page_count
        )

    def relocate_pdf(self, project: Project, new_pdf_path: str, current_page_count: int) -> bool:
        """
        Intenta relocalizar el PDF. Retorna True si tiene éxito (fingerprint coincide), False si falla.
        """
        try:
            sha256, size = self._compute_fingerprint(new_pdf_path)
            if (
                project.pdf_sha256 == sha256
                and project.pdf_size == size
                and project.pdf_page_count == current_page_count
            ):
                project.pdf_path = new_pdf_path
                project.updated_at = datetime.now(UTC)
                if self._project_repo:
                    self._project_repo.save(project)
                return True
        except FileNotFoundError:
            pass
        return False

    def bind_to_project_db(self, db_path: str):
        self.db_path = db_path
        self._project_repo = self._persistence_factory.create_project_repository(db_path)
        self.region_repo = self._persistence_factory.create_region_repository(db_path)
        self.glossary_repo = getattr(self._persistence_factory, "create_glossary_repository", lambda x: None)(db_path)
        self.uow = getattr(self._persistence_factory, "create_unit_of_work", lambda x: None)(db_path)

    def get_region_repository(self):
        return self.region_repo
