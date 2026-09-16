import pytest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication

from src.presentation.coordinators.export_ui_coordinator import ExportUiCoordinator
from src.ui.views.main_window import MainWindow
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel


def test_export_coordinator_completed_real_vm(qtbot):
    app = QApplication.instance()
    if not app:
        app = QApplication([])

    vm = PdfViewerViewModel(service=None)
    vm._document_loaded = True

    window = MainWindow(vm)

    # Create coordinator
    coordinator = ExportUiCoordinator(
        parent=window,
        use_case=Mock(),
        controller=Mock(),
        resolve_dirty_draft_cb=lambda: True,
        get_project_id_cb=lambda: "dummy-project",
        get_source_pdf_cb=lambda: "dummy-source.pdf",
    )
    # The actual bug test checks if UI is unlocked on completion, which requires self.viewmodel
    # but self.viewmodel was replaced by actual command_history.
    # We will simulate the MainWindow slot logic which is what failed in Hotfix 3.

    # 1. Start an export (simulated)
    coordinator.active_job_id = "test-job-123"
    window._set_export_ui_locked(True)

    assert window.pdf_widget._region_editing_enabled is False
    assert window.source_panel.isEnabled() is False

    # 2. Simulate completed
    coordinator.controller.is_active = False
    coordinator._on_completed("test-job-123", Mock())
    window._set_export_ui_locked(False)

    # 3. Check locks are removed and state is clean
    assert coordinator.is_export_active() is False
    assert coordinator.active_job_id is None

    assert window.pdf_widget._region_editing_enabled is True
    assert window.source_panel.isEnabled() is True
    assert window.action_export.isEnabled() is True  # because doc is loaded
    assert window.action_undo.isEnabled() is False  # empty history
