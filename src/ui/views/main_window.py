from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QToolBar, QWidget, QSizePolicy

from src.ui.components.pdf_view_widget import PdfViewWidget
from src.ui.components.region_list_panel import RegionListPanel
from src.ui.components.source_panel import SourcePanel
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel, ZoomMode


class MainWindow(QMainWindow):
    def __init__(self, viewmodel: PdfViewerViewModel):
        super().__init__()
        self.viewmodel = viewmodel
        self.setWindowTitle("Traductor PDF")
        self.resize(1024, 768)

        # UI Components
        self.pdf_widget = PdfViewWidget(self)
        self.setCentralWidget(self.pdf_widget)

        self.source_panel = SourcePanel(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.source_panel)
        self.region_panel = RegionListPanel(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.region_panel)

        self.export_coordinator = None

        self._create_toolbar()
        self._connect_viewmodel()

        self.source_panel.on_debug_toggled = self._on_debug_fragments_toggled
        self.source_panel.save_region_requested.connect(self.viewmodel.save_region)
        self.source_panel.on_edit_translation = self.viewmodel.edit_translation
        
        # TRANS-05 connections
        self.source_panel.review_requested.connect(self.viewmodel.mark_translation_reviewed)
        self.source_panel.approve_requested.connect(self.viewmodel.approve_translation)

        self.viewmodel.engine_info_changed.connect(self._on_engine_info_changed)

        # Inyectar dependencias del widget
        self.pdf_widget.get_mapper_func = self.viewmodel.get_mapper
        self.pdf_widget.get_text_preview_func = self.viewmodel.get_text_preview
        self.pdf_widget.on_selection_committed = self._on_selection_committed_intercept
        self.pdf_widget.on_selection_cleared = self._on_selection_cleared_intercept
        self.pdf_widget.on_region_selected = self._on_region_selected_intercept
        self.pdf_widget.on_region_geometry_changed = self.viewmodel.move_resize_region

    def set_export_coordinator(self, coordinator):
        self.export_coordinator = coordinator
        self.export_coordinator.set_lock_ui_callback(self._set_export_ui_locked)

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        # File menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        self.action_export = QAction("Export Translated PDF...", self)
        self.action_export.triggered.connect(self._on_export_clicked)
        self.action_export.setEnabled(False)
        file_menu.addAction(self.action_export)

        # Project menu
        project_menu = menubar.addMenu("Project")
        self.action_glossary = QAction("Glosario...", self)
        self.action_glossary.triggered.connect(self._on_glossary_clicked)
        self.action_glossary.setEnabled(False)
        project_menu.addAction(self.action_glossary)

        # File operations
        self.action_open = toolbar.addAction("Open")
        self.action_open.triggered.connect(self._on_open_clicked)
        toolbar.addSeparator()

        # Navigation
        self.action_prev = toolbar.addAction("Prev")
        self.action_prev.triggered.connect(self._on_prev_page)

        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(50)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.returnPressed.connect(self._on_page_input_return)
        toolbar.addWidget(self.page_input)

        self.page_count_label = QLabel(" / 0")
        toolbar.addWidget(self.page_count_label)

        self.action_next = toolbar.addAction("Next")
        self.action_next.triggered.connect(self._on_next_page)
        toolbar.addSeparator()

        # Undo / Redo
        self.action_undo = QAction("Undo", self)
        self.action_undo.setShortcut("Ctrl+Z")
        self.action_undo.triggered.connect(self._on_undo)
        self.action_undo.setEnabled(False)
        toolbar.addAction(self.action_undo)

        self.action_redo = QAction("Redo", self)
        self.action_redo.setShortcut("Ctrl+Y")
        self.action_redo.triggered.connect(self._on_redo)
        self.action_redo.setEnabled(False)
        toolbar.addAction(self.action_redo)
        toolbar.addSeparator()
        # Zoom controls
        self.action_zoom_out = toolbar.addAction("-")
        self.action_zoom_out.triggered.connect(self.viewmodel.zoom_out)

        self.zoom_label = QLabel("100%")
        toolbar.addWidget(self.zoom_label)

        self.action_zoom_in = toolbar.addAction("+")
        self.action_zoom_in.triggered.connect(self.viewmodel.zoom_in)
        toolbar.addSeparator()

        # Fit controls
        self.action_actual = toolbar.addAction("Actual")
        self.action_actual.triggered.connect(
            lambda: self.viewmodel.set_zoom_mode(ZoomMode.ACTUAL_SIZE)
        )

        self.action_fit_width = toolbar.addAction("Fit Width")
        self.action_fit_width.triggered.connect(
            lambda: self.viewmodel.set_zoom_mode(ZoomMode.FIT_WIDTH)
        )

        self.action_fit_page = toolbar.addAction("Fit Page")
        self.action_fit_page.triggered.connect(
            lambda: self.viewmodel.set_zoom_mode(ZoomMode.FIT_PAGE)
        )
        toolbar.addSeparator()

        # Selection
        self.action_select = toolbar.addAction("Select Region")
        self.action_select.setCheckable(True)
        self.action_select.toggled.connect(self.viewmodel.set_selection_mode)
        toolbar.addSeparator()

        # Preview
        self.action_preview = toolbar.addAction("Preview Translations")
        self.action_preview.setCheckable(True)
        self.action_preview.toggled.connect(self.viewmodel.toggle_preview)

        # Engine status (right-aligned via spacer)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.engine_status_label = QLabel("Engine: Checking...")
        self.engine_status_label.setContentsMargins(0, 0, 10, 0)
        toolbar.addWidget(self.engine_status_label)

        self._update_ui_state()

    def _connect_viewmodel(self):
        self.viewmodel.document_loaded_changed.connect(self._on_document_loaded_changed)
        self.viewmodel.current_page_changed.connect(self._on_current_page_changed)
        self.viewmodel.page_count_changed.connect(self._on_page_count_changed)
        self.viewmodel.zoom_mode_changed.connect(self.pdf_widget.set_zoom_mode)
        self.viewmodel.zoom_factor_changed.connect(self._on_zoom_factor_changed)
        self.viewmodel.page_rendered.connect(self.pdf_widget.set_rendered_page)
        self.viewmodel.error_occurred.connect(self._show_error)

        self.viewmodel.selection_mode_changed.connect(self._on_selection_mode_changed)
        self.viewmodel.selection_changed.connect(self.pdf_widget.set_current_selection)
        self.viewmodel.preview_toggled.connect(self._on_preview_toggled)
        self.viewmodel.extraction_completed.connect(self.source_panel.update_result)
        self.viewmodel.can_undo_changed.connect(self.action_undo.setEnabled)
        self.viewmodel.can_redo_changed.connect(self.action_redo.setEnabled)
        self.viewmodel.saved_regions_changed.connect(self.pdf_widget.set_saved_regions)
        self.viewmodel.saved_regions_changed.connect(self.region_panel.set_regions)
        self.viewmodel.selected_saved_region_changed.connect(self.source_panel.show_saved_region)
        self.viewmodel.selected_saved_region_changed.connect(
            lambda r: self.region_panel.select_region(r.id if r else None)
        )
        self.viewmodel.selected_saved_region_changed.connect(
            lambda r: self.pdf_widget.select_saved_region(r.id if r else None)
        )
        self.region_panel.region_selected.connect(self._on_region_selected_intercept)
        self.region_panel.delete_region_requested.connect(self._on_delete_region_intercept)
        self.source_panel.delete_region_requested.connect(self._on_delete_region_intercept)

        self.viewmodel.project_locked_changed.connect(
            lambda locked: self.source_panel.set_project_unlocked(not locked)
        )
        self.viewmodel.translation_in_flight_changed.connect(
            self.source_panel.set_translation_in_flight
        )
        self.source_panel.translate_region_requested.connect(self.viewmodel.translate_region)
        
        # Batch Connections
        self.region_panel.batch_widget.translate_all_requested.connect(self._on_translate_pending_clicked)
        self.region_panel.batch_widget.cancel_batch_requested.connect(self.viewmodel.cancel_batch)
        self.region_panel.batch_widget.retry_failed_requested.connect(self.viewmodel.retry_failed_batch)
        
        self.viewmodel.batch_progress.connect(self.region_panel.batch_widget.update_progress)
        self.viewmodel.batch_finished.connect(self.region_panel.batch_widget.on_batch_finished)
        self.viewmodel.saved_regions_changed.connect(self._update_batch_pending_state)

    @Slot(bool)
    def _on_document_loaded_changed(self, loaded: bool):
        self._update_ui_state()

    @Slot(int)
    def _on_current_page_changed(self, page: int):
        self.page_input.setText(str(page))
        self._update_ui_state()

    @Slot(int)
    def _on_page_count_changed(self, count: int):
        self.page_count_label.setText(f" / {count}")
        self._update_ui_state()

    @Slot(float)
    def _on_zoom_factor_changed(self, factor: float):
        self.zoom_label.setText(f"{int(factor * 100)}%")
        self.pdf_widget.set_zoom_factor(factor)
        # Refrescar selección para que reajuste su pen thickness
        self.pdf_widget.set_current_selection(self.viewmodel.current_selection)
        self.viewmodel._refresh_saved_regions()

    @Slot(bool)
    def _on_selection_mode_changed(self, enabled: bool):
        self.action_select.setChecked(enabled)
        self.pdf_widget.set_selection_mode(enabled)

    @Slot(bool)
    def _on_preview_toggled(self, enabled: bool):
        self.action_preview.setChecked(enabled)
        self.pdf_widget.set_preview_mode(enabled)

    @Slot(str)
    def _show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)

    def _on_debug_fragments_toggled(self, state: bool):
        if state and self.viewmodel.extraction_result:
            rects = [f.bbox for f in self.viewmodel.extraction_result.fragments]
            self.pdf_widget.set_debug_rects(rects, self.viewmodel.get_mapper())
        else:
            self.pdf_widget.set_debug_rects([])

    def _update_ui_state(self):
        loaded = self.viewmodel.document_loaded

        self.action_prev.setEnabled(loaded and self.viewmodel.current_page > 1)
        self.action_next.setEnabled(
            loaded and self.viewmodel.current_page < self.viewmodel.page_count
        )

        self.page_input.setEnabled(loaded)

        self.action_zoom_in.setEnabled(loaded)
        self.action_zoom_out.setEnabled(loaded)
        self.action_actual.setEnabled(loaded)
        self.action_fit_width.setEnabled(loaded)
        self.action_fit_page.setEnabled(loaded)
        self.action_select.setEnabled(loaded)
        self.action_preview.setEnabled(loaded)

        # Enable Export only if loaded and no export is currently active
        export_active = self.export_coordinator and self.export_coordinator.is_export_active()
        self.action_export.setEnabled(loaded and not export_active)
        self.action_glossary.setEnabled(loaded)

    def _set_export_ui_locked(self, locked: bool):
        # We must ensure critical panels are unlocked even if cosmetic properties fail
        disabled = locked

        # 1. Critical restoration
        self.source_panel.setEnabled(not disabled)
        self.region_panel.setEnabled(not disabled)

        try:
            self.pdf_widget.set_region_editing_enabled(not disabled)
        except Exception as e:
            from src.application.logger import logger

            logger.error(f"Failed to unlock region editing: {e}")

        # 2. Cosmetic / secondary state restoration
        try:
            self.action_export.setEnabled(not disabled and self.viewmodel.document_loaded)
            self.action_open.setEnabled(not disabled)
            self.action_undo.setEnabled(not disabled and self.viewmodel.can_undo)
            self.action_redo.setEnabled(not disabled and self.viewmodel.can_redo)

            self.action_select.setEnabled(not disabled and self.viewmodel.document_loaded)
            if disabled:
                if self.action_select.isChecked():
                    self.action_select.setChecked(False)
                    self.pdf_widget.set_selection_mode(False)
        except Exception as e:
            from src.application.logger import logger

            logger.error(f"Failed to restore cosmetic actions: {e}")

        # Navigation remains enabled

    def _on_export_clicked(self):
        if self.viewmodel and hasattr(self.viewmodel, 'batch_coordinator') and self.viewmodel.batch_coordinator.is_active:
            from PySide6.QtWidgets import QMessageBox
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("Traducciones Activas")
            msg_box.setText("Hay traducciones todavía en curso. La exportación utilizará únicamente las regiones que ya se encuentran completadas y guardadas.")
            btn_continue = msg_box.addButton("Continuar exportación", QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = msg_box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec_()
            if msg_box.clickedButton() == btn_cancel:
                return

        if self.export_coordinator:
            self.export_coordinator.start_export_flow()

    def _on_glossary_clicked(self):
        from src.ui.views.glossary_dialog import GlossaryDialog
        if self.viewmodel._project_service and self.viewmodel._project_service._project_repo:
            project_id = self.viewmodel._project_service.db_path.split("/")[-2] if "/" in self.viewmodel._project_service.db_path else self.viewmodel._project_service.db_path.split("\\")[-2]
            # Fetch current project
            project = self.viewmodel._project_service.open_project(project_id)
            dialog = GlossaryDialog(self.viewmodel._project_service, project, self)
            dialog.exec_()

    def _on_open_clicked(self):
        if not self.source_panel.resolve_dirty_draft():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if file_path:
            self.viewmodel.open_document(file_path)

    def _on_page_input_return(self):
        if not self.source_panel.resolve_dirty_draft():
            self.page_input.setText(str(self.viewmodel.current_page))
            return
        text = self.page_input.text()
        try:
            page_num = int(text)
            success = self.viewmodel.go_to_page(page_num)
            if not success:
                self.page_input.setText(str(self.viewmodel.current_page))
        except ValueError:
            self.page_input.setText(str(self.viewmodel.current_page))

    def _on_prev_page(self):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.previous_page()

    def _on_next_page(self):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.next_page()


    def _on_engine_info_changed(self, info):
        if not hasattr(self, "engine_status_label"):
            return
        if not info:
            self.engine_status_label.setText("Engine: Unknown")
            return
            
        status_text = info.status.value
        
        # Make fake engine explicitly visible
        if info.provider.lower() == "fake" or "fake" in info.provider.lower():
            color = "#8b5cf6" # purple for dev
            text = f"Dev Engine (Fake) - {status_text}"
        else:
            color = "#22c55e" if info.status.value == "ready" else "#ef4444"
            text = f"Ollama ({info.model}) - {status_text}"
            
        self.engine_status_label.setText(text)
        self.engine_status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _on_undo(self):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.undo()

    def _on_redo(self):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.redo()

    def _on_region_selected_intercept(self, region_id: str):
        if not self.source_panel.resolve_dirty_draft():
            # Restore visual selection to the current selected region
            self.pdf_widget.select_saved_region(self.viewmodel._selected_region_id)
            self.region_panel.select_region(self.viewmodel._selected_region_id)
            return
        self.viewmodel.select_region(region_id)

    def _on_selection_committed_intercept(self, rect):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.commit_selection(rect)

    def _on_selection_cleared_intercept(self):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.clear_selection()

    def _on_delete_region_intercept(self, region_id: str):
        if not self.source_panel.resolve_dirty_draft():
            return
        self.viewmodel.delete_region(region_id)

    def closeEvent(self, event):
        if self.export_coordinator:
            can_close = self.export_coordinator.handle_close_request()
            if not can_close:
                event.ignore()
                return

        if not self.source_panel.resolve_dirty_draft():
            event.ignore()
            return
        self.viewmodel.close_document()
        event.accept()

    def _update_batch_pending_state(self, regions):
        from src.domain.models.enums import RegionStatus
        has_pending = any(r.status != RegionStatus.TRANSLATED for r in regions)
        self.region_panel.batch_widget.set_has_pending(has_pending)

    def _on_translate_pending_clicked(self):
        if not self.viewmodel._current_project or not self.viewmodel._project_service:
            return
            
        regions = self.viewmodel._project_service.region_repo.get_by_page(self.viewmodel._current_project.id, self.viewmodel.current_page)
        from src.domain.models.enums import RegionStatus
        pending_ids = [r.id for r in regions if r.status != RegionStatus.TRANSLATED]
        
        if pending_ids:
            self.region_panel.batch_widget.set_active()
            self.viewmodel.start_batch(pending_ids)
