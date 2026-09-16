import pytest
from PySide6.QtWidgets import QApplication

from src.ui.views.main_window import MainWindow
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


def test_main_window_lock_with_real_vm(qtbot):
    app = QApplication.instance()
    if not app:
        app = QApplication([])

    vm = PdfViewerViewModel(service=None)
    # Using real viewmodel
    window = MainWindow(vm)

    # 1. Lock
    window._set_export_ui_locked(True)

    assert window.pdf_widget._region_editing_enabled is False
    assert window.action_export.isEnabled() is False
    assert window.source_panel.isEnabled() is False
    assert window.region_panel.isEnabled() is False

    assert window.action_undo.isEnabled() is False
    assert window.action_redo.isEnabled() is False

    # 2. Unlock
    window._set_export_ui_locked(False)

    # Editing restored
    assert window.pdf_widget._region_editing_enabled is True
    # Export only enabled if document loaded
    assert window.action_export.isEnabled() is False  # Because vm.document_loaded is False
    assert window.source_panel.isEnabled() is True
    assert window.region_panel.isEnabled() is True

    # Undo/redo should reflect real VM state (False initially)
    assert window.action_undo.isEnabled() is False
    assert window.action_redo.isEnabled() is False

    # 3. Simulate VM having document and undo state
    vm._document_loaded = True
    # To simulate command, we could execute a dummy command, but it's enough to verify
    # that _set_export_ui_locked reads the vm properly without crashing.

    window._set_export_ui_locked(False)
    assert window.action_export.isEnabled() is True
