from unittest.mock import Mock

from PySide6.QtWidgets import QApplication

from src.ui.views.main_window import MainWindow


def test_viewer_lock_during_export():
    app = QApplication.instance()
    if not app:
        app = QApplication([])

    # Setup mock viewmodel
    mock_vm = Mock()
    mock_vm.document_loaded = True
    mock_vm.can_undo = True
    mock_vm.can_redo = True
    mock_vm.current_page = 1
    mock_vm.page_count = 1

    # Needs a real application for MainWindow, pytest-qt handles this if qtbot is present.
    window = MainWindow(mock_vm)

    # Initial state
    window.action_select.setChecked(True)
    window.pdf_widget.set_selection_mode(True)

    assert window.pdf_widget._is_selection_mode is True
    assert window.pdf_widget._region_editing_enabled is True

    # 1. Lock (Export starts)
    window._set_export_ui_locked(True)

    # Region editing and selection should be disabled
    assert window.pdf_widget._region_editing_enabled is False
    assert window.action_select.isChecked() is False
    assert window.pdf_widget._is_selection_mode is False
    assert window.action_select.isEnabled() is False

    # Other panels
    assert window.source_panel.isEnabled() is False
    assert window.region_panel.isEnabled() is False

    # 2. Unlock (Export terminal)
    window._set_export_ui_locked(False)

    # Region editing should be enabled again
    assert window.pdf_widget._region_editing_enabled is True
    # Action select enabled but NOT automatically checked again
    assert window.action_select.isEnabled() is True
    assert window.action_select.isChecked() is False
    assert window.pdf_widget._is_selection_mode is False

    # Panels enabled
    assert window.source_panel.isEnabled() is True
    assert window.region_panel.isEnabled() is True
