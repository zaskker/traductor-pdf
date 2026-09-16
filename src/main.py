import os
import sys

from PySide6.QtWidgets import QApplication

from src.application.logger import logger
from src.application.services.pdf_viewer_service import PdfViewerService
from src.application.services.project_service import ProjectService
from src.application.services.text_extraction import TextExtractionService
from src.composition.translation import create_translation_engine
from src.infrastructure.pdf.adapter import PyMuPDFDocument
from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine
from src.infrastructure.pdf.preview_renderer import PyMuPDFTextPreviewRenderer
from src.infrastructure.persistence.factory import SqlitePersistenceFactory
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel
from src.ui.views.main_window import MainWindow


def main():
    if "--worker" in sys.argv:
        worker_idx = sys.argv.index("--worker")
        if worker_idx + 1 < len(sys.argv) and sys.argv[worker_idx + 1] == "export":
            from src.workers.pdf_export_worker import main as worker_main
            sys.exit(worker_main())

    logger.info("Iniciando Traductor PDF - Fase 3 (Extracción)")

    app = QApplication(sys.argv)

    # 1. Infrastructure
    pdf_adapter = PyMuPDFDocument()
    persistence_factory = SqlitePersistenceFactory()
    project_service = ProjectService(persistence_factory)

    # 2. Application
    pdf_service = PdfViewerService(pdf_adapter)
    extraction_service = TextExtractionService(pdf_adapter.get_text_extractor())
    text_layout_engine = PyMuPDFTextLayoutEngine()
    text_preview_renderer = PyMuPDFTextPreviewRenderer()

    # 4. Config & Translation Engine Composition
    try:
        engine = create_translation_engine(os.environ)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to configure translation engine: {e}")
        sys.exit(1)

    if engine.__class__.__name__ == "FakeTranslationEngine":
        engine.configured_mapping = {"Hello": "Hola"}

    source_language = os.environ.get("SOURCE_LANGUAGE", "English").strip()
    target_language = os.environ.get("TARGET_LANGUAGE", "Spanish").strip()

    from src.composition.export_factory import ExportFactory
    preview_use_case = ExportFactory.create_prepare_preview_use_case()

    # 5. ViewModel
    viewmodel = PdfViewerViewModel(
        service=pdf_service,
        extraction_service=extraction_service,
        project_service=project_service,
        translation_engine=engine,
        text_layout_engine=text_layout_engine,
        text_preview_renderer=text_preview_renderer,
        source_language=source_language,
        target_language=target_language,
        preview_use_case=preview_use_case,
    )

    class ProjectRepoProxy:
        def get(self, project_id):
            return project_service._project_repo.get(project_id)

    class RegionRepoProxy:
        def get_all(self, project_id):
            # Delegamos al repositorio real instanciado por project_service
            return project_service.get_region_repository().get_all(project_id)

    from src.composition.export_factory import ExportFactory
    from src.infrastructure.process.export_controller import ExportProcessController

    use_case = ExportFactory.create_prepare_export_use_case(ProjectRepoProxy(), RegionRepoProxy())
    controller = ExportProcessController()

    # 4. View
    window = MainWindow(viewmodel)

    from src.presentation.coordinators.export_ui_coordinator import ExportUiCoordinator

    coordinator = ExportUiCoordinator(
        parent=window,
        use_case=use_case,
        controller=controller,
        resolve_dirty_draft_cb=window.source_panel.resolve_dirty_draft,
        get_project_id_cb=lambda: (
            viewmodel.current_project.id if viewmodel.current_project else None
        ),
        get_source_pdf_cb=lambda: (
            viewmodel.current_project.pdf_path if viewmodel.current_project else None
        ),
    )
    window.set_export_coordinator(coordinator)

    logger.info("Mostrando ventana principal.")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
