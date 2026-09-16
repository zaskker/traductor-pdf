from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
from src.infrastructure.pdf.background_analyzer import PyMuPDFRegionBackgroundAnalyzer
from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine
from src.infrastructure.pdf.source_inspector import PyMuPDFPdfSourceInspector
from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter


class ExportFactory:
    """
    Assembles the dependencies required for Phase 9A Export.
    """

    @staticmethod
    def create_prepare_export_use_case(project_repo, region_repo) -> PreparePdfExportUseCase:
        return PreparePdfExportUseCase(
            project_repo=project_repo,
            region_repo=region_repo,
            source_inspector=PyMuPDFPdfSourceInspector(),
            background_analyzer=PyMuPDFRegionBackgroundAnalyzer(),
            layout_engine=PyMuPDFTextLayoutEngine(),
        )

    @staticmethod
    def create_vector_form_exporter() -> PyMuPDFVectorFormPdfExporter:
        return PyMuPDFVectorFormPdfExporter()

    @staticmethod
    def create_prepare_preview_use_case() -> "PrepareRegionPreviewUseCase":
        from src.application.use_cases.prepare_region_preview_use_case import PrepareRegionPreviewUseCase
        from src.application.services.region_render_spec_planner import RegionRenderSpecPlanner

        planner = RegionRenderSpecPlanner(
            background_analyzer=PyMuPDFRegionBackgroundAnalyzer(),
            layout_engine=PyMuPDFTextLayoutEngine()
        )
        return PrepareRegionPreviewUseCase(
            source_inspector=PyMuPDFPdfSourceInspector(),
            planner=planner
        )
