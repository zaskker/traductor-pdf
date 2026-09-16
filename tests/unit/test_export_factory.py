from unittest.mock import Mock

from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
from src.composition.export_factory import ExportFactory
from src.infrastructure.pdf.background_analyzer import PyMuPDFRegionBackgroundAnalyzer
from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine
from src.infrastructure.pdf.source_inspector import PyMuPDFPdfSourceInspector
from src.infrastructure.pdf.vector_form_exporter import PyMuPDFVectorFormPdfExporter


def test_export_factory_composition_smoke():
    project_repo = Mock()
    region_repo = Mock()

    # 1. Create use case
    use_case = ExportFactory.create_prepare_export_use_case(project_repo, region_repo)

    assert isinstance(use_case, PreparePdfExportUseCase)
    assert use_case._project_repo is project_repo
    assert use_case._region_repo is region_repo
    assert isinstance(use_case._source_inspector, PyMuPDFPdfSourceInspector)
    assert isinstance(use_case._background_analyzer, PyMuPDFRegionBackgroundAnalyzer)
    assert isinstance(use_case._layout_engine, PyMuPDFTextLayoutEngine)

    # 2. Create exporter
    exporter = ExportFactory.create_vector_form_exporter()
    assert isinstance(exporter, PyMuPDFVectorFormPdfExporter)
