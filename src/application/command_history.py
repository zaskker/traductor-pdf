from typing import Protocol


class Command(Protocol):
    def execute(self) -> None:
        pass

    def undo(self) -> None:
        pass

    def redo(self) -> None:
        pass


class CommandHistory:
    """
    Gestor atómico del historial de comandos.
    El índice muta SOLAMENTE si las operaciones no lanzan excepciones.
    """

    def __init__(self):
        self._commands: list[Command] = []
        self._current_index = 0

    @property
    def can_undo(self) -> bool:
        return self._current_index > 0

    @property
    def can_redo(self) -> bool:
        return self._current_index < len(self._commands)

    def execute(self, command: Command) -> None:
        """
        Ejecuta un nuevo comando. Si tiene éxito, se trunca el redo-branch,
        se apila y se avanza el índice.
        """
        command.execute()

        # Si llegamos aquí, execute() no lanzó excepciones.
        # Truncar la rama de Redo.
        self._commands = self._commands[: self._current_index]
        self._commands.append(command)
        self._current_index += 1

    def undo(self) -> None:
        """
        Deshace el comando en el índice actual.
        El índice se decrementa solo si no hay excepciones.
        """
        if not self.can_undo:
            return

        command = self._commands[self._current_index - 1]
        command.undo()

        # Si llegamos aquí, undo() tuvo éxito.
        self._current_index -= 1

    def redo(self) -> None:
        """
        Rehace el próximo comando.
        El índice se incrementa solo si no hay excepciones.
        """
        if not self.can_redo:
            return

        command = self._commands[self._current_index]
        command.redo()

        # Si llegamos aquí, redo() tuvo éxito.
        self._current_index += 1

    def clear(self) -> None:
        """Descarta el historial sin ejecutar undo."""
        self._commands.clear()
        self._current_index = 0
