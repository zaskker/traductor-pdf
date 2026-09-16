import uuid
from enum import Enum

from PySide6.QtCore import QObject, Signal, Slot

from src.application.command_history import Command, CommandHistory
from src.application.dtos.pdf_selection import PdfSelection
from src.application.services.batch_coordinator import TranslationBatchCoordinator, BatchSnapshot
from src.application.ports.text_layout_engine import ITextLayoutEngine
from src.application.services.pdf_viewer_service import PdfViewerService
from src.application.services.project_service import ProjectService
from src.application.services.text_extraction import TextExtractionService
from src.application.dtos.translation_execution_config import TranslationExecutionConfig
from src.domain.interfaces.translation import ITranslationEngine, TranslationEngineInfo, EngineStatus
from src.domain.models.project import Project
from src.domain.value_objects.extraction import TextExtractionResult
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.layout import TextLayoutResult


class ZoomMode(Enum):
    ACTUAL_SIZE = "ACTUAL_SIZE"
    FIT_WIDTH = "FIT_WIDTH"
    FIT_PAGE = "FIT_PAGE"
    CUSTOM = "CUSTOM"


class PdfViewerViewModel(QObject):
    # Signals to notify the View
    document_loaded_changed = Signal(bool)
    current_page_changed = Signal(int)
    page_count_changed = Signal(int)
    zoom_mode_changed = Signal(ZoomMode)
    zoom_factor_changed = Signal(float)  # The visual zoom applied (QTransform scale)
    page_rendered = Signal(object)  # RenderedPage
    document_closed = Signal()
    project_loaded = Signal(object)  # Project
    project_locked_changed = Signal(bool)
    saved_regions_changed = Signal(list)  # list[TranslationRegion]
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    error_occurred = Signal(str)

    # Selection
    selection_mode_changed = Signal(bool)
    selection_changed = Signal(object)  # PdfSelection | None
    extraction_completed = Signal(object)  # TextExtractionResult | None
    selected_saved_region_changed = Signal(object)  # TranslationRegion | None
    translation_in_flight_changed = Signal(str, bool)  # region_id, is_in_flight
    engine_info_changed = Signal(object)
    preview_toggled = Signal(bool)

    batch_progress = Signal(int, int) # completed, total
    batch_finished = Signal(dict) # summary
    
    def __init__(
        self,
        service: PdfViewerService,
        extraction_service=None,
        project_service: ProjectService | None = None,
        translation_engine: ITranslationEngine | None = None,
        text_layout_engine: ITextLayoutEngine | None = None,
        text_preview_renderer=None,  # ITextPreviewRenderer
        source_language: str = "English",
        target_language: str = "Spanish",
        preview_use_case=None,
    ):
        super().__init__()
        self._service = service
        self._extraction_service = extraction_service
        self._project_service = project_service
        self._translation_engine = translation_engine
        self._text_layout_engine = text_layout_engine
        self._text_preview_renderer = text_preview_renderer
        self._source_language = source_language
        self._target_language = target_language
        self._preview_use_case = preview_use_case

        self._current_project: Project | None = None
        self._is_project_locked = False
        self._command_history = CommandHistory()

        self._document_loaded = False
        self._current_page = 0
        self._page_count = 0

        self._zoom_mode = ZoomMode.FIT_WIDTH
        self._zoom_factor = 1.0  # 1.0 = 100% (logical Actual Size)

        # Translation state
        self.in_flight_region_ids: set[str] = set()
        self.active_workers: set[object] = set()
        self.active_translations: dict[str, object] = {}
        self.batch_coordinator = TranslationBatchCoordinator(
            dispatch_callback=self._dispatch_batch_job,
            on_progress_callback=self.batch_progress.emit,
            on_finished_callback=self.batch_finished.emit
        )
        
        if self._translation_engine:
            self._check_engine_availability()

        # Rendición inicial estática. Un valor > 1.0 mejora la resolución base.
        # En el futuro esto podría ser dinámico basado en zoom.
        self._render_scale = 1.5

        # Selection
        self._is_selection_mode = False
        self._current_selection: PdfSelection | None = None
        self._extraction_result: TextExtractionResult | None = None
        self._selected_region_id: str | None = None

        self._is_preview_enabled = False
        self._session_id = None

        # Cache de layout
        self._layout_cache: dict[tuple, TextLayoutResult] = {}
        self._raster_cache: dict[tuple, object] = {}  # RenderedTextPreview

    @property
    def current_project(self) -> Project | None:
        return self._current_project

    @property
    def is_project_locked(self) -> bool:
        return self._is_project_locked

    @property
    def document_loaded(self) -> bool:
        return self._document_loaded

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    @property
    def is_selection_mode(self) -> bool:
        return self._is_selection_mode

    @property
    def is_preview_enabled(self) -> bool:
        return self._is_preview_enabled

    @property
    def current_selection(self) -> PdfSelection | None:
        return self._current_selection

    @property
    def can_undo(self) -> bool:
        return self._command_history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._command_history.can_redo

    def open_document(self, file_path: str):
        import os
        if not os.path.exists(file_path):
            self.error_occurred.emit(f"PDF file not found: {file_path}")
            return
            
        import pymupdf as fitz
        try:
            doc = fitz.open(file_path)
            if doc.needs_pass:
                doc.close()
                self.error_occurred.emit("Este PDF está protegido con contraseña y no puede abrirse en esta versión.")
                return
            doc.close()
        except Exception as e:  # noqa: BLE001
            self.error_occurred.emit("El PDF está corrupto o es inválido y no se puede abrir.")
            return

        if self._document_loaded:
            self.close_document()
            
        try:
            self._session_id = str(uuid.uuid4())
            self._service.open_document(file_path)

            # Load or create project
            if self._project_service:
                page_count = self._service.get_page_count()
                proj, _db_path = self._project_service.discover_or_create_project(
                    file_path, page_count
                )
                self._current_project = proj

                is_locked = self._project_service.check_project_locked(proj, file_path, page_count)
                self._is_project_locked = is_locked

                if proj.last_viewed_page > 0:
                    self._service.go_to_page(proj.last_viewed_page)

                self.project_loaded.emit(proj)
                self.project_locked_changed.emit(is_locked)

            self._update_document_state(True)
            self._current_page = -1  # force update
            self._on_page_changed()
        except Exception as e:  # noqa: BLE001
            self.error_occurred.emit(str(e))
            self.close_document()

    def close_document(self):
        self._session_id = None
        self._service.close_document()
        self._current_project = None
        self._is_project_locked = False
        self._command_history.clear()
        if self.batch_coordinator.is_active:
            self.batch_coordinator.cancel_batch()
        self.in_flight_region_ids.clear()
        self._emit_undo_redo_state()
        self._update_document_state(False)
        self.document_closed.emit()
        self.clear_selection()
        self.page_rendered.emit(None)
        self.saved_regions_changed.emit([])

    def _update_document_state(self, loaded: bool):
        if self._document_loaded != loaded:
            self._document_loaded = loaded
            self.document_loaded_changed.emit(self._document_loaded)
            if not loaded:
                self.clear_selection()

        page_count = self._service.get_page_count()
        if self._page_count != page_count:
            self._page_count = page_count
            self.page_count_changed.emit(self._page_count)

    def _refresh_saved_regions(self):
        if (
            self._project_service
            and self._current_project
            and self._document_loaded
            and self._project_service.region_repo
        ):
            regions = self._project_service.region_repo.get_by_page(
                self._current_project.id, self._current_page
            )
            self.saved_regions_changed.emit(regions)

            # Re-emit selected region if it was selected and updated
            if self._selected_region_id:
                self.select_region(self._selected_region_id)

    def _on_page_changed(self):
        current_page = self._service.get_current_page_number()
        if self._current_page != current_page:
            if self._project_service and self._current_project and self._document_loaded:
                self._project_service.update_last_viewed_page(self._current_project, current_page)
            self._current_page = current_page
            self.current_page_changed.emit(self._current_page)
            self.clear_selection()
            self._trigger_render()
            self._refresh_saved_regions()

    def next_page(self):
        if self._service.next_page():
            self._on_page_changed()

    def previous_page(self):
        if self._service.previous_page():
            self._on_page_changed()

    def go_to_page(self, page_number: int) -> bool:
        if self._service.go_to_page(page_number):
            self._on_page_changed()
            return True
        return False

    def _trigger_render(self):
        if not self._document_loaded:
            return
        try:
            # Renderizamos asíncronamente en una app real, pero sincrónico para Fase 1
            rendered_page = self._service.render_current_page(render_scale=self._render_scale)
            self.page_rendered.emit(rendered_page)
        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            self.error_occurred.emit(str(e))

    # --- Zoom Controls ---
    def set_zoom_mode(self, mode: ZoomMode):
        if self._zoom_mode != mode:
            self._zoom_mode = mode
            self.zoom_mode_changed.emit(self._zoom_mode)

            # If changing to ACTUAL_SIZE, enforce zoom factor immediately
            if mode == ZoomMode.ACTUAL_SIZE:
                self.set_custom_zoom(1.0)

    def set_custom_zoom(self, factor: float):
        # Limit zoom between 25% and 400%
        factor = max(0.25, min(4.0, factor))
        if self._zoom_factor != factor:
            self._zoom_factor = factor
            self.zoom_factor_changed.emit(self._zoom_factor)

            # Si seteamos un custom zoom manualmente y no era via Actual Size
            if self._zoom_mode != ZoomMode.ACTUAL_SIZE and self._zoom_mode != ZoomMode.CUSTOM:
                self.set_zoom_mode(ZoomMode.CUSTOM)

    def zoom_in(self):
        self.set_custom_zoom(self._zoom_factor * 1.25)
        self.set_zoom_mode(ZoomMode.CUSTOM)

    def zoom_out(self):
        self.set_custom_zoom(self._zoom_factor * 0.8)
        self.set_zoom_mode(ZoomMode.CUSTOM)

    # --- Selection Controls ---
    def set_selection_mode(self, enabled: bool):
        if self._is_selection_mode != enabled:
            self._is_selection_mode = enabled
            self.selection_mode_changed.emit(self._is_selection_mode)

    def toggle_preview(self, enabled: bool):
        if self._is_preview_enabled != enabled:
            self._is_preview_enabled = enabled
            self.preview_toggled.emit(self._is_preview_enabled)
            # Emit saved regions changed to force recreation of preview items
            self._refresh_saved_regions()

    def clear_selection(self):
        self._current_selection = None
        self._extraction_result = None
        self.selection_changed.emit(None)
        self.extraction_completed.emit(None)

    def select_region(self, region_id: str | None):
        # Desactivamos mode "Create" si había algo
        self.clear_selection()
        self._selected_region_id = region_id

        # Encontramos la región guardada
        if (
            region_id
            and self._project_service
            and self._project_service.region_repo
            and self._current_project
        ):
            region = self._project_service.region_repo.get(region_id)
            if region:
                self.selected_saved_region_changed.emit(region)
            else:
                self.selected_saved_region_changed.emit(None)
        else:
            self.selected_saved_region_changed.emit(None)

    def commit_selection(self, rendered_rect: Rect):
        if not self._document_loaded:
            return

        mapper = self._service.get_coordinate_mapper(self._render_scale)
        if not mapper:
            return

        pdf_rect = mapper.rendered_rect_to_pdf(rendered_rect)

        selection = PdfSelection(page_number=self._current_page, pdf_rect=pdf_rect)

        # FIX: Clear any active saved region context when making a new temporary selection
        if self._selected_region_id:
            self._selected_region_id = None
            self.selected_saved_region_changed.emit(None)

        self._current_selection = selection
        self.selection_changed.emit(self._current_selection)

        # Trigger Extraction automatically on commit
        if self._extraction_service:
            self._extraction_result = self._extraction_service.extract_from_selection(
                self._current_selection
            )
            self.extraction_completed.emit(self._extraction_result)

    def get_mapper(self):
        """
        Expone el mapper actual al UI para que pueda proyectar selecciones
        (por ej. al redibujar el overlay tras zoom).
        """
        if not self._document_loaded:
            return None
        return self._service.get_coordinate_mapper(self._render_scale)

    def save_region(self):
        if not self._current_project or self._is_project_locked:
            return
        if not self._current_selection or not self._extraction_result:
            return

        from src.application.commands import CreateRegionCommand
        from src.application.use_cases.create_region import CreateTranslationRegionUseCase

        use_case = CreateTranslationRegionUseCase()
        region = use_case.execute(
            self._current_project, self._current_selection, self._extraction_result
        )

        if self._project_service and self._project_service.region_repo:
            cmd = CreateRegionCommand(region, self._project_service.region_repo)
            self.execute_command(cmd, self.on_region_saved_successfully)

    def on_region_saved_successfully(self):
        self.clear_selection()
        self._trigger_render()
        self._refresh_saved_regions()

    def move_resize_region(self, region_id: str, new_rendered_rect: Rect):
        if not self._current_project or self._is_project_locked:
            self._refresh_saved_regions()  # Revert UI to saved state
            return

        if not self._project_service or not self._project_service.region_repo:
            return

        repo = self._project_service.region_repo
        old_region = repo.get(region_id)
        if not old_region:
            return

        mapper = self._service.get_coordinate_mapper(self._render_scale)
        if not mapper:
            return

        # QRectF -> PDF-native Rect
        # Asumimos que new_rendered_rect es un QRectF, lo convertimos a nuestro Rect
        from src.application.commands import MoveResizeRegionCommand
        from src.application.use_cases.move_resize_region import (
            MoveResizeRegionError,
            MoveResizeRegionUseCase,
        )
        from src.domain.value_objects.geometry import Rect as DomainRect

        r = DomainRect(
            new_rendered_rect.left(),
            new_rendered_rect.top(),
            new_rendered_rect.right(),
            new_rendered_rect.bottom(),
        )
        pdf_rect = mapper.rendered_rect_to_pdf(r)

        use_case = MoveResizeRegionUseCase(self._extraction_service)
        try:
            new_region = use_case.execute(
                self._current_project, old_region, pdf_rect, self._is_project_locked
            )
            cmd = MoveResizeRegionCommand(old_region, new_region, repo)
            self.execute_command(
                cmd, on_success=self._refresh_saved_regions, on_error=self._refresh_saved_regions
            )
        except MoveResizeRegionError:
            # Revert visual state
            self._refresh_saved_regions()
            # self.error_occurred.emit(str(e)) # Opt: No arrojar error por no-text, solo cancelar

    def delete_region(self, region_id: str):
        if not self._current_project or self._is_project_locked:
            return

        from src.application.commands import DeleteRegionCommand

        cmd = DeleteRegionCommand(region_id, self._project_service.region_repo)
        self.execute_command(cmd, self._refresh_saved_regions)

    def execute_command(self, command: Command, on_success=None, on_error=None):
        try:
            self._command_history.execute(command)
            self._emit_undo_redo_state()
            if on_success:
                on_success()
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error()
            self.error_occurred.emit(str(e))

    def undo(self):
        try:
            self._command_history.undo()
            self._emit_undo_redo_state()
            self._refresh_saved_regions()
        except Exception as e:  # noqa: BLE001
            self.error_occurred.emit(str(e))

    def redo(self):
        try:
            self._command_history.redo()
            self._emit_undo_redo_state()
            self._refresh_saved_regions()
        except Exception as e:  # noqa: BLE001
            self.error_occurred.emit(str(e))

    def _emit_undo_redo_state(self):
        self.can_undo_changed.emit(self._command_history.can_undo)
        self.can_redo_changed.emit(self._command_history.can_redo)

    def edit_translation(self, region_id: str, new_text: str) -> bool:
        """Applies a manual edit to a translated region."""
        if self._is_project_locked:
            self.error_occurred.emit("Project is locked.")
            return False

        from src.application.commands import EditTranslationCommand
        from src.application.use_cases.edit_translation import EditTranslationUseCase

        use_case = EditTranslationUseCase(self._project_service.region_repo)
        try:
            # Check for no-op edit
            region = self._project_service.region_repo.get(region_id)
            if region and region.translated_text == new_text:
                return True

            old_snapshot, new_snapshot = use_case.execute(region_id, new_text)
            command = EditTranslationCommand(
                old_region=old_snapshot,
                new_region=new_snapshot,
                repo=self._project_service.region_repo,
            )
            self._command_history.execute(command)

            self._refresh_saved_regions()
            # If the edited region is currently selected, refresh it
            if self._selected_region_id == region_id:
                region = self._project_service.region_repo.get(region_id)
                self.selected_saved_region_changed.emit(region)

            self._emit_undo_redo_state()
            return True

        except Exception as e:  # noqa: BLE001
            from src.application.logger import logger

            logger.error(f"Failed to edit translation: {e}")
            self.error_occurred.emit(f"Failed to edit translation: {e}")
            return False

    @Slot(str)
    def translate_region(self, region_id: str):
        if not self._current_project or self._is_project_locked:
            return
        if not self._project_service or not self._project_service.region_repo:
            return
        if not self._translation_engine:
            return

        if region_id in self.in_flight_region_ids:
            return

        region = self._project_service.region_repo.get(region_id)
        if not region:
            return

        if not region.source_text or not region.source_text.strip():
            return

        self.in_flight_region_ids.add(region_id)
        self.translation_in_flight_changed.emit(region_id, True)

        from PySide6.QtCore import QThreadPool

        from src.application.services.prompt_builder import TranslationPromptBuilder
        from src.application.services.token_protector import TokenProtector
        from src.application.use_cases.translate_region import (
            TranslateRegionRequest,
            TranslateRegionUseCase,
        )
        from src.ui.viewmodels.translation_worker import TranslationWorker

        use_case = TranslateRegionUseCase(
            engine=self._translation_engine,
            repository=self._project_service.region_repo,
            project_repository=self._project_service._project_repo,
            glossary_repository=self._project_service.glossary_repo,
            token_protector=TokenProtector(),
            prompt_builder=TranslationPromptBuilder(),
            memory_repository=self._project_service.uow.translation_memory_repository if self._project_service.uow else None,
        )

        request = TranslateRegionRequest(
            region_id=region_id,
            source_language=self._source_language,
            target_language=self._target_language,
            project_locked=self._is_project_locked,
        )

        worker = TranslationWorker(
            use_case=use_case,
            request=request,
            region_id=region_id,
            project_id=self._current_project.id,
            source_text=region.source_text,
            updated_at=region.updated_at,
            session_id=self._session_id,
        )

        worker.signals.finished.connect(
            lambda old_r, new_r, w=worker: self._on_translation_finished(old_r, new_r, w)
        )
        worker.signals.error.connect(lambda code, msg, w=worker: self._on_translation_error(code, msg, w))

        self.active_workers.add(worker)
        self.active_translations[region_id] = worker
        QThreadPool.globalInstance().start(worker)


    def start_batch(self, region_ids: list[str]):
        if not self._current_project or self._is_project_locked:
            return
            
        if self.batch_coordinator.is_active:
            return
        
        # Filter out already in-flight regions
        ids_to_queue = [r for r in region_ids if r not in self.in_flight_region_ids]
        if not ids_to_queue:
            return
            
        active_glossary_id = None
        active_glossary_revision = None
        glossary_entries = []
        if self._project_service and self._project_service.glossary_repo:
            active_glossary_id = self._project_service.glossary_repo.get_active_glossary_id(self._current_project.id)
            if active_glossary_id:
                glossary = self._project_service.glossary_repo.get(active_glossary_id)
                if glossary:
                    active_glossary_revision = glossary.revision
                    glossary_entries = list(glossary.entries)

        config = TranslationExecutionConfig(
            source_language=self._source_language,
            target_language=self._target_language,
            engine=self._translation_engine,
            glossary_id=active_glossary_id,
            glossary_revision=active_glossary_revision,
            glossary_entries=glossary_entries
        )
        snapshot = BatchSnapshot(config)
        self.batch_coordinator.start_batch(ids_to_queue, snapshot)
        
    def cancel_batch(self):
        self.batch_coordinator.cancel_batch()
        
    def retry_failed_batch(self):
        self.batch_coordinator.retry_failed()

    def _dispatch_batch_job(self, region_id: str, batch_id: str, snapshot: BatchSnapshot):
        if region_id in self.in_flight_region_ids:
            # Manually started in the meantime, skip for batch
            self.batch_coordinator.report_job_finished(region_id, batch_id, success=False, error_msg="Duplicate request")
            return
            
        self.in_flight_region_ids.add(region_id)
        # Notify coordinator we actually started
        self.batch_coordinator.report_job_started(region_id, batch_id)
        
        region = self._project_service.region_repo.get(region_id)
        if not region or not region.source_text:
            self.batch_coordinator.report_job_finished(region_id, batch_id, success=False, error_msg="Region deleted or empty")
            return
            
        from PySide6.QtCore import QThreadPool
        from src.application.services.prompt_builder import TranslationPromptBuilder
        from src.application.services.token_protector import TokenProtector
        from src.application.use_cases.translate_region import TranslateRegionRequest, TranslateRegionUseCase
        from src.ui.viewmodels.translation_worker import TranslationWorker
        
        # We must use snapshot's config
        use_case = TranslateRegionUseCase(
            engine=snapshot.config.engine,
            repository=self._project_service.region_repo,
            project_repository=self._project_service._project_repo,
            glossary_repository=self._project_service.glossary_repo,
            token_protector=TokenProtector(),
            prompt_builder=TranslationPromptBuilder(),
            memory_repository=self._project_service.uow.translation_memory_repository if self._project_service.uow else None,
        )
        
        request = TranslateRegionRequest(
            region_id=region_id,
            config=snapshot.config,
            project_locked=self._is_project_locked,
        )
        
        worker = TranslationWorker(
            use_case=use_case,
            request=request,
            region_id=region_id,
            project_id=self._current_project.id,
            source_text=region.source_text,
            updated_at=region.updated_at,
            session_id=self._session_id,
            batch_id=batch_id,
        )
        
        worker.signals.finished.connect(
            lambda old_r, new_r, w=worker: self._on_translation_finished(old_r, new_r, w)
        )
        worker.signals.error.connect(lambda code, msg, w=worker: self._on_translation_error(code, msg, w))

        self.active_workers.add(worker)
        self.active_translations[region_id] = worker
        QThreadPool.globalInstance().start(worker)

    def mark_translation_reviewed(self, region_id: str, expected_revision: int):
        if not self._project_service or not self._project_service.region_repo:
            return

        from src.application.use_cases.mark_translation_reviewed import MarkTranslationReviewedUseCase
        from src.domain.interfaces.translation import StaleTranslationRevisionError
        
        try:
            uc = MarkTranslationReviewedUseCase(self._project_service.region_repo)
            _old, new_snapshot = uc.execute(region_id, expected_revision)
            
            # Update UI
            self._refresh_saved_regions()
            
            # Note: No CommandHistory update because review is not undoable
        except StaleTranslationRevisionError as e:
            self.error_occurred.emit(str(e))
            self._refresh_saved_regions()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def approve_translation(self, region_id: str, expected_revision: int):
        if not self._project_service or not self._project_service.region_repo:
            return

        from src.application.use_cases.approve_translation import ApproveTranslationUseCase
        from src.domain.interfaces.translation import StaleTranslationRevisionError, TranslationNotReviewedError
        
        try:
            uc = ApproveTranslationUseCase(self._project_service.uow)
            _old, new_snapshot = uc.execute(region_id, expected_revision)
            
            # Update UI
            self._refresh_saved_regions()
            
        except (StaleTranslationRevisionError, TranslationNotReviewedError) as e:
            self.error_occurred.emit(str(e))
            self._refresh_saved_regions()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _check_engine_availability(self):
        from src.application.logger import logger

        # Emit initial info synchronously if the engine supports it.
        # Mocks / legacy engines may lack get_info; productive engines must implement it.
        is_mock = "Mock" in type(self._translation_engine).__name__

        if hasattr(self._translation_engine, "get_info"):
            try:
                self.engine_info_changed.emit(self._translation_engine.get_info())
            except Exception as e:
                logger.warning(f"engine.get_info() raised {type(e).__name__}: {e}")
        elif not is_mock:
            # Engines that claim to be productive must implement the contract.
            raise NotImplementedError(
                f"Translation engine {type(self._translation_engine).__name__!r} must implement get_info()"
            )

        # Schedule an async availability check if supported
        if not hasattr(self._translation_engine, "check_availability"):
            if not is_mock:
                raise NotImplementedError(
                    f"Translation engine {type(self._translation_engine).__name__!r} must implement check_availability()"
                )
            return

        import weakref
        from PySide6.QtCore import QThreadPool, QRunnable
        vm_ref = weakref.ref(self)
        engine = self._translation_engine
        class EngineCheckWorker(QRunnable):
            def run(self):
                info = engine.check_availability()
                vm = vm_ref()
                if vm is not None:
                    try:
                        vm.engine_info_changed.emit(info)
                    except RuntimeError:
                        pass  # Signal source deleted — VM was GC'd between check and emit
        worker = EngineCheckWorker()
        QThreadPool.globalInstance().start(worker)

    def _cleanup_worker(self, worker):
        if worker in self.active_workers:
            self.active_workers.remove(worker)

        if worker.session_id == self._session_id:
            if self.active_translations.get(worker.region_id) == worker:
                del self.active_translations[worker.region_id]
                self.in_flight_region_ids.discard(worker.region_id)
                self.translation_in_flight_changed.emit(worker.region_id, False)

    def _on_translation_finished(self, old_region, new_region, worker):
        if worker.session_id != self._session_id or self.active_translations.get(worker.region_id) != worker:
            self._cleanup_worker(worker)
            if getattr(worker, "batch_id", None):
                self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=False, error_msg="Stale session")
            return

        self._cleanup_worker(worker)

        # Stale validation
        if not self._current_project or self._current_project.id != worker.project_id:
            if getattr(worker, "batch_id", None):
                self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=False, error_msg="Project changed")
            return  # Project changed

        repo = self._project_service.region_repo
        current_region = repo.get(worker.region_id)
        if not current_region:
            if getattr(worker, "batch_id", None):
                self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=False, error_msg="Region deleted")
            return
            
        repo.save(new_region)
        self.saved_regions_changed.emit(repo.get_by_page(self._current_project.id, self._current_page))
        
        if getattr(worker, "batch_id", None):
            self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=True)
            
        # Prevent Preview Storm: only render heavily if this region is selected
        if self._selected_region_id == worker.region_id:
            self.selected_saved_region_changed.emit(new_region)
            self._trigger_render()

        if (
            current_region.updated_at != worker.updated_at or current_region.source_text != worker.source_text
        ):
            if getattr(worker, "batch_id", None):
                self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=False, error_msg="Stale source text or changed during translation")
            return  # Region modified (e.g. moved or resized)
        
        if current_region.is_manually_edited:
            if getattr(worker, "batch_id", None):
                self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=False, error_msg="Region manually edited")
            return  # Region was manually edited while translation was in flight

        from src.application.commands import TranslateRegionCommand

        cmd = TranslateRegionCommand(old_region, new_region, repo)

        # We don't want repo errors to show aggressive modals as instructed: "Si repo falla: history unchanged, UI refreshed from repository, in-flight cleared, error visible"
        # execute_command will emit error_occurred. That is acceptable for visibility.
        self.execute_command(
            cmd, on_success=self._refresh_saved_regions, on_error=self._refresh_saved_regions
        )
        if getattr(worker, "batch_id", None):
            self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=True)

    def _on_translation_error(self, error_code: str, error_msg: str, worker):
        is_active = (worker.session_id == self._session_id and self.active_translations.get(worker.region_id) == worker)
        self._cleanup_worker(worker)
        if getattr(worker, "batch_id", None):
            self.batch_coordinator.report_job_finished(worker.region_id, worker.batch_id, success=False, error_code=error_code, error_msg=error_msg)
        if not is_active:
            return
            
        if error_code == "STRUCTURAL_MARKER_MISMATCH":
            display_msg = "La traducción no pudo completarse porque el modelo devolvió una respuesta con formato inválido. Podés volver a intentarlo."
        else:
            display_msg = f"Translation failed: {error_msg}"
            
        self.error_occurred.emit(display_msg)

    def get_text_layout(self, region_id: str) -> TextLayoutResult | None:
        if (
            not self._text_layout_engine
            or not self._project_service
            or not self._project_service.region_repo
        ):
            return None

        region = self._project_service.region_repo.get(region_id)
        if not region or not region.translated_text:
            return None

        from src.application.services.layout_factory import TextLayoutRequestFactory

        input_data = TextLayoutRequestFactory.create_input(region)
        if not input_data:
            return None

        cache_key = (
            input_data.text,
            input_data.target_rect.width,
            input_data.target_rect.height,
            input_data.min_font_size,
            input_data.max_font_size,
            input_data.font_family,
        )

        if cache_key in self._layout_cache:
            return self._layout_cache[cache_key]

        result = self._text_layout_engine.layout_text(input_data)
        self._layout_cache[cache_key] = result
        return result

    def get_text_preview(self, region_id: str) -> tuple[object | None, object | None, object | None, tuple[int, int, int] | None]:
        if not self._preview_use_case or not self._project_service or not self._project_service.region_repo or not self._current_project:
            return None, None, None, None
            
        region = self._project_service.region_repo.get(region_id)
        if not region or not region.translated_text:
            return None, None, None, None
            
        all_regions = self._project_service.region_repo.get_by_page(self._current_project.id, region.page_id)
        
        preview = self._preview_use_case.execute(
            source_path=self._current_project.pdf_path,
            region=region,
            all_regions=all_regions
        )
        
        if not preview:
            return None, None, None, None
            
        render_scale = 2.0
        
        # New robust cache key
        blocks_tuple = tuple((b.text, b.rect, b.font_size, b.alignment, b.wrap_mode) for b in preview.plan.blocks)
        
        cache_key = (
            region.translated_text,
            blocks_tuple,
            preview.overlay_rect,
            preview.background_rgb,
            render_scale
        )

        if cache_key in self._raster_cache:
            return preview.plan, self._raster_cache[cache_key], preview.overlay_rect, preview.background_rgb
            
        try:
            rendered = self._text_preview_renderer.render_preview(
                preview.overlay_rect,
                preview.plan.blocks,
                render_scale,
                preview.background_rgb
            )
            self._raster_cache[cache_key] = rendered
            return preview.plan, rendered, preview.overlay_rect, preview.background_rgb
        except Exception as e:
            from src.application.logger import logger
            logger.error(f"Failed to render preview raster: {e}")
            return preview.plan, None, preview.overlay_rect, preview.background_rgb
