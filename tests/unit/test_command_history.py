import pytest

from src.application.command_history import Command, CommandHistory


class MockCommand(Command):
    def __init__(self, should_fail_execute=False, should_fail_undo=False, should_fail_redo=False):
        self.should_fail_execute = should_fail_execute
        self.should_fail_undo = should_fail_undo
        self.should_fail_redo = should_fail_redo
        self.executed = False
        self.undone = False

    def execute(self) -> None:
        if self.should_fail_execute:
            raise RuntimeError("Execute failed")
        self.executed = True

    def undo(self) -> None:
        if self.should_fail_undo:
            raise RuntimeError("Undo failed")
        self.executed = False
        self.undone = True

    def redo(self) -> None:
        if self.should_fail_redo:
            raise RuntimeError("Redo failed")
        self.executed = True
        self.undone = False


def test_command_history_basic_execute_undo_redo():
    history = CommandHistory()
    cmd1 = MockCommand()
    cmd2 = MockCommand()

    history.execute(cmd1)
    assert history._current_index == 1
    assert history.can_undo is True
    assert history.can_redo is False

    history.execute(cmd2)
    assert history._current_index == 2

    history.undo()
    assert history._current_index == 1
    assert cmd2.undone is True
    assert cmd2.executed is False

    history.redo()
    assert history._current_index == 2
    assert cmd2.executed is True


def test_command_history_execute_failure():
    history = CommandHistory()
    cmd = MockCommand(should_fail_execute=True)

    with pytest.raises(RuntimeError):
        history.execute(cmd)

    assert history._current_index == 0
    assert history.can_undo is False
    assert len(history._commands) == 0


def test_command_history_undo_failure_is_atomic():
    history = CommandHistory()
    cmd = MockCommand()
    history.execute(cmd)

    assert history._current_index == 1

    cmd.should_fail_undo = True
    with pytest.raises(RuntimeError):
        history.undo()

    assert history._current_index == 1
    assert history.can_undo is True

    # Retry success
    cmd.should_fail_undo = False
    history.undo()
    assert history._current_index == 0
    assert history.can_undo is False
    assert history.can_redo is True


def test_command_history_redo_failure_is_atomic():
    history = CommandHistory()
    cmd = MockCommand()
    history.execute(cmd)
    history.undo()

    assert history._current_index == 0
    assert history.can_redo is True

    cmd.should_fail_redo = True
    with pytest.raises(RuntimeError):
        history.redo()

    assert history._current_index == 0
    assert history.can_redo is True

    # Retry success
    cmd.should_fail_redo = False
    history.redo()
    assert history._current_index == 1


def test_command_history_branch_after_undo():
    history = CommandHistory()
    cmdA = MockCommand()
    cmdB = MockCommand()
    cmdC = MockCommand()

    history.execute(cmdA)
    history.execute(cmdB)
    assert history._current_index == 2

    history.undo()
    assert history._current_index == 1

    history.execute(cmdC)
    assert history._current_index == 2
    assert len(history._commands) == 2
    assert history._commands[1] == cmdC


def test_command_history_clear():
    history = CommandHistory()
    history.execute(MockCommand())
    history.execute(MockCommand())

    assert history.can_undo is True
    history.clear()

    assert history.can_undo is False
    assert history.can_redo is False
    assert history._current_index == 0
    assert len(history._commands) == 0


def test_cross_project_history():
    history = CommandHistory()

    # Project A
    cmdA = MockCommand()
    history.execute(cmdA)
    assert history.can_undo is True

    # Close Project A -> Open Project B
    history.clear()
    assert history.can_undo is False
    assert history.can_redo is False
