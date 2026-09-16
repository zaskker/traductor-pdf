from typing import Protocol

from src.domain.interfaces.persistence import ITranslationRegionRepository
from src.domain.models.region import TranslationRegion


class CommandExecutionError(Exception):
    pass


class Command(Protocol):
    def execute(self) -> None:
        pass

    def undo(self) -> None:
        pass

    def redo(self) -> None:
        pass


class CreateRegionCommand(Command):
    def __init__(self, region: TranslationRegion, repo: ITranslationRegionRepository):
        self.region = region
        self.repo = repo
        self._executed = False

    def execute(self) -> None:
        try:
            self.repo.save(self.region)
            self._executed = True
        except Exception as e:
            raise CommandExecutionError(f"Create failed: {e}") from e

    def undo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.delete(self.region.id)
        except Exception as e:
            raise CommandExecutionError(f"Undo create failed: {e}") from e

    def redo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.region)
        except Exception as e:
            raise CommandExecutionError(f"Redo create failed: {e}") from e


class DeleteRegionCommand(Command):
    def __init__(self, region_id: str, repo: ITranslationRegionRepository):
        self.region_id = region_id
        self.repo = repo
        self._snapshot: TranslationRegion | None = None
        self._executed = False

    def execute(self) -> None:
        self._snapshot = self.repo.get(self.region_id)
        if not self._snapshot:
            raise CommandExecutionError("Region not found to delete")

        try:
            self.repo.delete(self.region_id)
            self._executed = True
        except Exception as e:
            raise CommandExecutionError(f"Delete failed: {e}") from e

    def undo(self) -> None:
        if not self._executed or not self._snapshot:
            return
        try:
            self.repo.save(self._snapshot)
        except Exception as e:
            raise CommandExecutionError(f"Undo delete failed: {e}") from e

    def redo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.delete(self.region_id)
        except Exception as e:
            raise CommandExecutionError(f"Redo delete failed: {e}") from e


class MoveResizeRegionCommand(Command):
    def __init__(
        self,
        old_region: TranslationRegion,
        new_region: TranslationRegion,
        repo: ITranslationRegionRepository,
    ):
        self.old_region = old_region
        self.new_region = new_region
        self.repo = repo
        self._executed = False

    def execute(self) -> None:
        try:
            self.repo.save(self.new_region)
            self._executed = True
        except Exception as e:
            raise CommandExecutionError(f"Move/Resize failed: {e}") from e

    def undo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.old_region)
        except Exception as e:
            raise CommandExecutionError(f"Undo Move/Resize failed: {e}") from e

    def redo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.new_region)
        except Exception as e:
            raise CommandExecutionError(f"Redo Move/Resize failed: {e}") from e


class TranslateRegionCommand(Command):
    def __init__(
        self,
        old_region: TranslationRegion,
        new_region: TranslationRegion,
        repo: ITranslationRegionRepository,
    ):
        self.old_region = old_region
        self.new_region = new_region
        self.repo = repo
        self._executed = False

    def execute(self) -> None:
        try:
            self.repo.save(self.new_region)
            self._executed = True
        except Exception as e:
            raise CommandExecutionError(f"Translate failed: {e}") from e

    def undo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.old_region)
        except Exception as e:
            raise CommandExecutionError(f"Undo Translate failed: {e}") from e

    def redo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.new_region)
        except Exception as e:
            raise CommandExecutionError(f"Redo Translate failed: {e}") from e


class EditTranslationCommand(Command):
    def __init__(
        self,
        old_region: TranslationRegion,
        new_region: TranslationRegion,
        repo: ITranslationRegionRepository,
    ):
        self.old_region = old_region
        self.new_region = new_region
        self.repo = repo
        self._executed = False

    def execute(self) -> None:
        try:
            self.repo.save(self.new_region)
            self._executed = True
        except Exception as e:
            raise CommandExecutionError(f"Edit translation failed: {e}") from e

    def undo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.old_region)
        except Exception as e:
            raise CommandExecutionError(f"Undo Edit translation failed: {e}") from e

    def redo(self) -> None:
        if not self._executed:
            return
        try:
            self.repo.save(self.new_region)
        except Exception as e:
            raise CommandExecutionError(f"Redo Edit translation failed: {e}") from e
