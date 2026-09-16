import os
import uuid
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from src.application.dtos.export import PendingRegionPolicy
from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
from src.infrastructure.process.export_controller import ExportProcessController, ExportProcessState
from src.presentation.ui.export_preflight_mapper import map_export_error, map_preflight_issues
from src.presentation.ui.export_progress_dialog import ExportProgressDialog
from src.presentation.ui.export_success_dialog import ExportSuccessDialog


class ExportUiCoordinator(QObject):
    def __init__(
        self,
        parent: QObject,
        use_case: PreparePdfExportUseCase,
        controller: ExportProcessController,
        resolve_dirty_draft_cb: Callable[[], bool],
        get_project_id_cb: Callable[[], str | None],
        get_source_pdf_cb: Callable[[], str | None],
    ):
        super().__init__(parent)
        self.parent_widget = parent
        self.use_case = use_case
        self.controller = controller
        self.resolve_dirty_draft_cb = resolve_dirty_draft_cb
        self.get_project_id_cb = get_project_id_cb
        self.get_source_pdf_cb = get_source_pdf_cb

        self.progress_dialog: ExportProgressDialog | None = None
        self.cancel_timer: QTimer | None = None

        self.active_destination: str | None = None
        self.active_job_id: str | None = None
        self._close_after_export = False
        self._last_progress = None

        self._set_ui_locked = lambda locked: None  # Callback set by MainWindow

    def set_lock_ui_callback(self, cb: Callable[[bool], None]):
        self._set_ui_locked = cb

    def is_export_active(self) -> bool:
        return self.controller.is_active

    def start_export_flow(self):
        if self.is_export_active():
            return

        project_id = self.get_project_id_cb()
        source_pdf = self.get_source_pdf_cb()

        if not project_id or not source_pdf:
            return

        if not self.resolve_dirty_draft_cb():
            return

        default_dest = source_pdf.replace(".pdf", "_translated.pdf")
        if default_dest == source_pdf:
            default_dest = source_pdf + "_translated.pdf"

        while True:
            options = QFileDialog.Options()
            options |= QFileDialog.DontConfirmOverwrite
            dest_path, _ = QFileDialog.getSaveFileName(
                self.parent_widget, "Export Translated PDF", default_dest, "PDF Files (*.pdf)", options=options
            )

            if not dest_path:
                return

            # Source == Destination check
            try:
                abs_source = os.path.normcase(os.path.abspath(source_pdf))
                abs_dest = os.path.normcase(os.path.abspath(dest_path))

                is_same = abs_source == abs_dest
                if not is_same and os.path.exists(source_pdf) and os.path.exists(dest_path):
                    is_same = os.path.samefile(source_pdf, dest_path)

                if is_same:
                    QMessageBox.warning(
                        self.parent_widget,
                        "Invalid Destination",
                        "No se puede sobrescribir el PDF original. Elegí otro nombre o ubicación.",
                    )
                    continue
            except FileNotFoundError:
                pass  # Dest doesn't exist yet, which is fine

            # Overwrite confirmation
            if os.path.exists(dest_path):
                reply = QMessageBox.question(
                    self.parent_widget,
                    "Replace File",
                    "El archivo de destino ya existe. ¿Deseás reemplazarlo?",
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
                if reply == QMessageBox.Cancel:
                    return

            break

        self._execute_preflight(project_id, dest_path, PendingRegionPolicy.BLOCK)

    def _execute_preflight(
        self,
        project_id: str,
        dest_path: str,
        pending_policy: PendingRegionPolicy,
        approval_policy: "ApprovalExportPolicy" = None,
    ):
        from src.application.dtos.export import ApprovalExportPolicy

        if approval_policy is None:
            approval_policy = ApprovalExportPolicy.APPROVED_ONLY

        # NOTE: Preflight is running sync for MVP.
        outcome = self.use_case.execute(
            project_id, dest_path, pending_policy=pending_policy, approval_policy=approval_policy
        )
        report = outcome.report

        if not report.can_export:
            # Check if blockers are exclusively policy-related (PENDING_REGIONS, UNAPPROVED_REGIONS)
            blockers = [iss for iss in report.issues if iss.severity.name == "BLOCKER"]
            
            # Since UNAPPROVED_REGIONS is a WARNING it won't be in blockers,
            # but we need to check if there are any unapproved regions warning
            warnings = [iss for iss in report.issues if iss.severity.name == "WARNING"]
            
            has_pending = any(iss.code.name == "PENDING_REGIONS" for iss in blockers)
            has_unapproved = any(iss.code.name == "UNAPPROVED_REGIONS" for iss in warnings)
            
            is_only_policy_blockers = all(iss.code.name == "PENDING_REGIONS" for iss in blockers)

            if is_only_policy_blockers and (has_pending or has_unapproved):
                # Construct combined question
                msg = ""
                if has_pending:
                    msg += f"• {report.pending_regions} regions pending translation.\n"
                if has_unapproved:
                    unapproved_msg = next((iss.message for iss in warnings if iss.code.name == "UNAPPROVED_REGIONS"), "translated regions not approved.")
                    msg += f"• {unapproved_msg}\n"
                    
                msg += "\nDo you want to export anyway? (Only translated/approved regions will be exported by default)"

                if has_unapproved:
                    # Show custom dialog with approval choice
                    reply = QMessageBox(self.parent_widget)
                    reply.setWindowTitle("Export Policy")
                    reply.setText(msg)
                    
                    btn_approved_only = reply.addButton("Exportar solo aprobadas", QMessageBox.ActionRole)
                    btn_all_translated = reply.addButton("Exportar todas las traducidas", QMessageBox.ActionRole)
                    btn_cancel = reply.addButton("Cancelar", QMessageBox.RejectRole)
                    
                    reply.exec()
                    clicked = reply.clickedButton()
                    
                    if clicked == btn_cancel:
                        return
                    elif clicked == btn_approved_only:
                        self._execute_preflight(
                            project_id, dest_path, PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, ApprovalExportPolicy.APPROVED_ONLY
                        )
                    elif clicked == btn_all_translated:
                        self._execute_preflight(
                            project_id, dest_path, PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, ApprovalExportPolicy.ALL_VALID_TRANSLATED
                        )
                    return
                else:
                    # Just pending
                    reply = QMessageBox.question(
                        self.parent_widget,
                        "Pending Regions",
                        msg,
                        QMessageBox.Yes | QMessageBox.Cancel,
                        QMessageBox.Cancel,
                    )
                    if reply == QMessageBox.Yes:
                        self._execute_preflight(
                            project_id, dest_path, PendingRegionPolicy.EXPORT_TRANSLATED_ONLY, approval_policy
                        )
                    return
            else:
                msg = map_preflight_issues(tuple(blockers))
                QMessageBox.warning(
                    self.parent_widget,
                    "Cannot Export PDF",
                    f"The project has issues that prevent exporting:\n\n{msg}",
                )
                return

        # Valid to start, but wait! What if it's can_export = True, but we have UNAPPROVED_REGIONS warning?
        warnings = [iss for iss in report.issues if iss.severity.name == "WARNING"]
        has_unapproved = any(iss.code.name == "UNAPPROVED_REGIONS" for iss in warnings)
        
        if has_unapproved and approval_policy == ApprovalExportPolicy.APPROVED_ONLY:
            unapproved_msg = next((iss.message for iss in warnings if iss.code.name == "UNAPPROVED_REGIONS"), "translated regions not approved.")
            msg = f"• {unapproved_msg}\n\nDo you want to export anyway?"
            
            reply = QMessageBox(self.parent_widget)
            reply.setWindowTitle("Export Policy")
            reply.setText(msg)
            
            btn_approved_only = reply.addButton("Exportar solo aprobadas", QMessageBox.ActionRole)
            btn_all_translated = reply.addButton("Exportar todas las traducidas", QMessageBox.ActionRole)
            btn_cancel = reply.addButton("Cancelar", QMessageBox.RejectRole)
            
            reply.exec()
            clicked = reply.clickedButton()
            
            if clicked == btn_cancel:
                return
            elif clicked == btn_approved_only:
                # Proceed with current request (it already filtered out unapproved)
                pass
            elif clicked == btn_all_translated:
                self._execute_preflight(
                    project_id, dest_path, pending_policy, ApprovalExportPolicy.ALL_VALID_TRANSLATED
                )
                return

        # Valid to start
        self._start_worker(project_id, dest_path, outcome.request)

    def _start_worker(self, project_id: str, dest_path: str, request):
        self.active_destination = dest_path
        self._set_ui_locked(True)

        self.progress_dialog = ExportProgressDialog(self.parent_widget)
        self.progress_dialog.cancel_requested.connect(self._on_cancel_requested)
        self.progress_dialog.force_stop_requested.connect(self._on_force_stop_requested)

        # Connect controller signals
        self.controller.started.connect(self._on_started)
        self.controller.progress.connect(self._on_progress)
        self.controller.finalizing.connect(self._on_finalizing)
        self.controller.completed.connect(self._on_completed)
        self.controller.cancelled.connect(self._on_cancelled)
        self.controller.failed.connect(self._on_failed)
        self.controller.crashed.connect(self._on_crashed)

        self.progress_dialog.show()

        # Start
        job_id = f"export_{project_id}_{uuid.uuid4().hex}"
        self.active_job_id = job_id
        self._last_progress = None

        try:
            self.controller.start(job_id, request)
        except Exception as e:
            self._finish_export_ui(job_id)
            QMessageBox.critical(self.parent_widget, "Export Error", str(e))

    def _on_started(self, job_id: str):
        if job_id != self.active_job_id:
            return
        if self.progress_dialog:
            self.progress_dialog.lbl_stage.setText("Running...")

    def _on_progress(self, job_id: str, prog):
        if job_id != self.active_job_id:
            return
        self._last_progress = prog
        if self.progress_dialog:
            self.progress_dialog.update_progress(
                prog.stage.name,
                prog.completed_regions,
                prog.total_regions,
                prog.completed_pages,
                prog.total_pages,
            )

    def _on_finalizing(self, job_id: str):
        if job_id != self.active_job_id:
            return
        if self.progress_dialog:
            if self._last_progress:
                self.progress_dialog.update_progress(
                    "FINALIZING",
                    self._last_progress.completed_regions,
                    self._last_progress.total_regions,
                    self._last_progress.completed_pages,
                    self._last_progress.total_pages,
                )
            else:
                self.progress_dialog.update_progress("FINALIZING", 0, 0, 0, 0)
        if self.cancel_timer:
            self.cancel_timer.stop()
            self.cancel_timer = None

    def _on_cancel_requested(self):
        self.controller.cancel()

        # Start timeout for force stop
        self.cancel_timer = QTimer(self)
        self.cancel_timer.setSingleShot(True)
        self.cancel_timer.timeout.connect(self._on_cancel_timeout)
        self.cancel_timer.start(5000)  # 5 seconds

        if self._close_after_export and self.progress_dialog:
            self.progress_dialog.lbl_stage.setText("Cancelling and closing...")

    def _on_cancel_timeout(self):
        if self.controller.state == ExportProcessState.FINALIZING:
            return
        if self.progress_dialog:
            self.progress_dialog.show_force_stop_option()

    def _on_force_stop_requested(self):
        self.controller.force_stop()

    def _on_completed(self, job_id: str, result):
        if job_id != self.active_job_id:
            return
        dest = self.active_destination
        self._finish_export_ui(job_id)

        if dest:
            dialog = ExportSuccessDialog(
                self.parent_widget, dest, result.exported_regions, result.pages_touched
            )
            dialog.exec()

    def _on_cancelled(self, job_id: str, payload):
        if job_id != self.active_job_id:
            return

        # Guardar si debemos cerrar antes de _finish_export_ui, ya que finish limpia la variable.
        should_close = self._close_after_export
        self._finish_export_ui(job_id)

        if payload.cleanup_failed and payload.temporary_path:
            QMessageBox.warning(
                self.parent_widget,
                "Export Cancelled",
                f"Export cancelled, but a temporary file could not be removed:\n{payload.temporary_path}",
            )
        else:
            if not should_close:
                QMessageBox.information(self.parent_widget, "Export Cancelled", "Export cancelled.")

    def _on_failed(self, job_id: str, err):
        if job_id != self.active_job_id:
            return
        self._finish_export_ui(job_id)
        msg = map_export_error(err.error_code)
        QMessageBox.critical(self.parent_widget, "Export Failed", f"{msg}")

    def _on_crashed(self, job_id: str, info):
        if job_id != self.active_job_id:
            return
        self._finish_export_ui(job_id)
        msg = map_export_error("PROCESS_CRASHED")
        QMessageBox.critical(
            self.parent_widget,
            "Export Crashed",
            f"{msg}\n\nReason: {info.get('reason', 'Unknown')}",
        )

    def _finish_export_ui(self, job_id: str = None):
        if job_id and job_id != self.active_job_id:
            return

        self.active_job_id = None

        if self.cancel_timer:
            self.cancel_timer.stop()
            self.cancel_timer = None

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None

        # Disconnect signals to avoid multiple triggers on repeated exports
        try:
            self.controller.started.disconnect(self._on_started)
            self.controller.progress.disconnect(self._on_progress)
            self.controller.finalizing.disconnect(self._on_finalizing)
            self.controller.completed.disconnect(self._on_completed)
            self.controller.cancelled.disconnect(self._on_cancelled)
            self.controller.failed.disconnect(self._on_failed)
            self.controller.crashed.disconnect(self._on_crashed)
        except Exception:
            pass

        self.active_destination = None
        self._set_ui_locked(False)

        should_close = self._close_after_export
        self._close_after_export = False

        if should_close:
            # Re-enter close event in the next event loop iteration
            QTimer.singleShot(0, self.parent_widget.close)

    def handle_close_request(self) -> bool:
        """Returns True if the app can close immediately, False if we need to wait for export cancellation."""
        if not self.is_export_active():
            return True

        if self.controller.state == ExportProcessState.FINALIZING:
            QMessageBox.information(
                self.parent_widget, "Exporting", "El PDF se está finalizando. Esperá unos segundos."
            )
            return False

        reply = QMessageBox.question(
            self.parent_widget,
            "Export in progress",
            "Export is still running. Do you want to cancel the export and close the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self._close_after_export = True
            if self.progress_dialog and not self.progress_dialog._is_cancelling:
                self.progress_dialog._on_cancel()
            else:
                self.controller.cancel()

        return False
