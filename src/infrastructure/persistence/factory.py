from src.domain.interfaces.persistence import (
    IProjectPersistenceFactory,
    IProjectRepository,
    ITranslationRegionRepository,
)
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import (
    SqliteProjectRepository,
    SqliteTranslationRegionRepository,
    SqliteGlossaryRepository,
)


class SqlitePersistenceFactory(IProjectPersistenceFactory):
    def __init__(self):
        self._db_cache: dict[str, Database] = {}

    def _get_db(self, db_path: str) -> Database:
        if db_path not in self._db_cache:
            db = Database(db_path)
            db.init_schema()
            self._db_cache[db_path] = db
        return self._db_cache[db_path]

    def create_unit_of_work(self, db_path: str) -> 'IUnitOfWork':
        from src.infrastructure.persistence.repository import SqliteUnitOfWork
        db = self._get_db(db_path)
        return SqliteUnitOfWork(db)

    def create_project_repository(self, db_path: str) -> IProjectRepository:
        db = self._get_db(db_path)
        return SqliteProjectRepository(db)

    def create_region_repository(self, db_path: str) -> ITranslationRegionRepository:
        db = self._get_db(db_path)
        return SqliteTranslationRegionRepository(db)

    def create_glossary_repository(self, db_path: str) -> IGlossaryRepository:
        from src.domain.interfaces.persistence import IGlossaryRepository
        db = self._get_db(db_path)
        return SqliteGlossaryRepository(db)

    def close_all(self):
        for db in self._db_cache.values():
            db.close()
        self._db_cache.clear()

    def backup(self, db_path: str, dest_path: str) -> None:
        db = self._get_db(db_path)
        db.backup(dest_path)
