from PySide6.QtCore import QObject, QRunnable, Signal

from src.application.use_cases.translate_region import (
    TranslateRegionRequest,
    TranslateRegionUseCase,
)


class TranslationWorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    - finished: Tuple[TranslationRegion, TranslationRegion] (old_region, new_region)
    - error: str (error message)
    """

    finished = Signal(object, object)
    error = Signal(str, str)  # error_code, error_message


class TranslationWorker(QRunnable):
    """
    Worker thread that executes TranslateRegionUseCase synchronously in the background.
    """

    def __init__(
        self,
        use_case: TranslateRegionUseCase,
        request: TranslateRegionRequest,
        region_id: str,
        project_id: str,
        source_text: str,
        updated_at,
        session_id: str,
        batch_id: str | None = None,
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.use_case = use_case
        self.request = request
        self.signals = TranslationWorkerSignals()

        # Stale validation tracking info
        self.region_id = region_id
        self.project_id = project_id
        self.source_text = source_text
        self.updated_at = updated_at
        self.session_id = session_id
        self.batch_id = batch_id

    def run(self):
        try:
            old_region, new_region = self.use_case.execute(self.request)
            print("WORKER SUCCESS:", new_region)
            self.signals.finished.emit(old_region, new_region)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("WORKER ERROR:", e)
            
            error_code = "UNKNOWN_ERROR"
            from src.domain.interfaces.translation import StructuralMarkerMismatchError, GlossaryMismatchError, TranslationTimeoutError, TranslationEngineUnavailableError, TranslationModelNotFoundError
            
            if isinstance(e, StructuralMarkerMismatchError):
                error_code = "STRUCTURAL_MARKER_MISMATCH"
            elif isinstance(e, GlossaryMismatchError):
                error_code = "GLOSSARY_MISMATCH"
            elif isinstance(e, TranslationTimeoutError):
                error_code = "TIMEOUT"
            elif isinstance(e, TranslationEngineUnavailableError):
                error_code = "ENGINE_UNAVAILABLE"
            elif isinstance(e, TranslationModelNotFoundError):
                error_code = "MODEL_NOT_FOUND"
                
            self.signals.error.emit(error_code, str(e))
