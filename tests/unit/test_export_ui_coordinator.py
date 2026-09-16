from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from src.application.dtos.export import PreflightOutcome, PreflightReport
from src.infrastructure.process.export_controller import (
    ExportCancellationPayload,
    ExportProcessState,
)
from src.presentation.coordinators.export_ui_coordinator import ExportUiCoordinator


@pytest.fixture
def mock_use_case():
    return Mock()


@pytest.fixture
def mock_controller():
    controller = Mock()
    controller.is_active = False
    controller.state = ExportProcessState.IDLE
    return controller


@pytest.fixture
def coordinator(mock_use_case, mock_controller):
    coord = ExportUiCoordinator(
        parent=None,
        use_case=mock_use_case,
        controller=mock_controller,
        resolve_dirty_draft_cb=Mock(return_value=True),
        get_project_id_cb=Mock(return_value="proj123"),
        get_source_pdf_cb=Mock(return_value="source.pdf"),
    )
    return coord


def test_dirty_draft_cancel(coordinator, mock_controller):
    coordinator.resolve_dirty_draft_cb.return_value = False
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName") as mock_dlg:
        coordinator.start_export_flow()
        mock_dlg.assert_not_called()
        mock_controller.start.assert_not_called()


def test_qfiledialog_cancel(coordinator, mock_controller):
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
        coordinator.start_export_flow()
        mock_controller.start.assert_not_called()


def test_source_equals_destination(coordinator, mock_controller):
    with (
        patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            side_effect=[("source.pdf", ""), ("", "")],
        ),
        patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn,
        patch("os.path.exists", return_value=True),
        patch("os.path.samefile", return_value=True),
    ):
        coordinator.start_export_flow()
        mock_warn.assert_called_once()
        mock_controller.start.assert_not_called()


def test_existing_destination_cancel(coordinator, mock_controller):
    with (
        patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            side_effect=[("dest.pdf", ""), ("", "")],
        ),
        patch("os.path.exists", return_value=True),
        patch("os.path.samefile", return_value=False),
        patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Cancel),
    ):
        coordinator.start_export_flow()
        mock_controller.start.assert_not_called()


def test_choose_another_destination(coordinator, mock_controller):
    with (
        patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            side_effect=[("dest.pdf", ""), ("", "")],
        ),
        patch("os.path.exists", return_value=True),
        patch("os.path.samefile", return_value=False),
        patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Cancel),
    ):
        coordinator.start_export_flow()
        mock_controller.start.assert_not_called()
        # Draft should only be resolved once
        coordinator.resolve_dirty_draft_cb.assert_called_once()


def test_valid_export_starts(coordinator, mock_use_case, mock_controller):
    report = PreflightReport(True, (), 10, 0, 0)
    mock_use_case.execute.return_value = PreflightOutcome(report, request=Mock())

    with (
        patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("dest.pdf", "")),
        patch("os.path.exists", return_value=False),
        patch("src.presentation.coordinators.export_ui_coordinator.ExportProgressDialog"),
        patch("os.path.samefile", return_value=False),
    ):
        coordinator.start_export_flow()
        mock_controller.start.assert_called_once()
        assert coordinator.active_job_id is not None
        assert coordinator.progress_dialog is not None


def test_stale_signals_ignored(coordinator, mock_controller):
    coordinator.active_job_id = "current_job"
    coordinator.progress_dialog = Mock()
    coordinator._last_progress = Mock()

    coordinator._on_started("old_job")
    coordinator._on_progress("old_job", Mock())
    coordinator._on_finalizing("old_job")

    coordinator.progress_dialog.lbl_stage.setText.assert_not_called()
    coordinator.progress_dialog.update_progress.assert_not_called()


def test_finalizing_preserves_counters(coordinator):
    coordinator.active_job_id = "job"
    coordinator.progress_dialog = Mock()
    prog = Mock()
    prog.completed_regions = 10
    prog.total_regions = 20
    prog.completed_pages = 1
    prog.total_pages = 2
    coordinator._last_progress = prog

    coordinator._on_finalizing("job")
    coordinator.progress_dialog.update_progress.assert_called_with("FINALIZING", 10, 20, 1, 2)


def test_handle_close_request_cancel(coordinator, mock_controller):
    mock_controller.is_active = True
    mock_controller.state = ExportProcessState.RUNNING
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes):
        can_close = coordinator.handle_close_request()
        assert not can_close
        mock_controller.cancel.assert_called_once()
        assert coordinator._close_after_export


def test_completed_success(coordinator, mock_controller):
    coordinator.active_job_id = "job"
    coordinator.active_destination = "dest.pdf"
    result = Mock()
    result.exported_regions = 10
    result.pages_touched = 2

    with patch(
        "src.presentation.coordinators.export_ui_coordinator.ExportSuccessDialog"
    ) as mock_dlg:
        coordinator._on_completed("job", result)
        mock_dlg.return_value.exec.assert_called_once()
        assert coordinator.active_job_id is None


def test_cancelled_cleanup_failed(coordinator):
    coordinator.active_job_id = "job"
    payload = ExportCancellationPayload(True, "temp.pdf")

    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
        coordinator._on_cancelled("job", payload)
        mock_warn.assert_called_once()
        assert coordinator.active_job_id is None


def test_close_after_export_reset(coordinator):
    coordinator.active_job_id = "job"
    coordinator._close_after_export = True
    coordinator.parent_widget = Mock()
    payload = ExportCancellationPayload(False, None)

    with (
        patch("PySide6.QtCore.QTimer.singleShot") as mock_timer,
        patch("PySide6.QtWidgets.QMessageBox.information"),
    ):
        coordinator._on_cancelled("job", payload)
        mock_timer.assert_called_once()
        assert coordinator._close_after_export is False
