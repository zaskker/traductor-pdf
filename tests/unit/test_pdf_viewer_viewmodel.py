import pytest
from PySide6.QtCore import QObject

from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.application.command_history import Command


class DummyCommand(Command):
    def __init__(self):
        self.executed = False
        self.undone = False

    def execute(self):
        self.executed = True

    def undo(self):
        self.undone = True


def test_pdf_viewer_viewmodel_undo_redo_state():
    vm = PdfViewerViewModel(service=None)

    # Track signals
    undo_states = []
    redo_states = []

    def on_can_undo(val):
        undo_states.append(val)

    def on_can_redo(val):
        redo_states.append(val)

    vm.can_undo_changed.connect(on_can_undo)
    vm.can_redo_changed.connect(on_can_redo)

    # 1. Initial state
    assert vm.can_undo is False
    assert vm.can_redo is False

    # 2. Execute command
    cmd1 = DummyCommand()
    vm.execute_command(cmd1)

    assert vm.can_undo is True
    assert vm.can_redo is False
    assert undo_states[-1] is True

    # 3. Undo
    vm.undo()
    assert vm.can_undo is False
    assert vm.can_redo is True
    assert undo_states[-1] is False
    assert redo_states[-1] is True
    assert cmd1.undone is True

    # 4. Redo
    vm.redo()
    assert vm.can_undo is True
    assert vm.can_redo is False
    assert redo_states[-1] is False
