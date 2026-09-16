import pytest
from unittest.mock import Mock, MagicMock
from src.application.use_cases.prepare_region_preview_use_case import PrepareRegionPreviewUseCase
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.application.dtos.export import ExportRegionSpec, PreflightIssue, PreflightIssueCode, PreflightSeverity

class TestPrepareRegionPreviewUseCase:
    @pytest.fixture
    def inspector_mock(self):
        inspector = Mock()
        inspection = Mock()
        inspection.page_cropboxes = {1: Rect(0, 0, 100, 100)}
        inspection.page_native_texts = {1: []}
        inspector.inspect.return_value = inspection
        return inspector

    @pytest.fixture
    def planner_mock(self):
        planner = Mock()
        return planner

    @pytest.fixture
    def use_case(self, inspector_mock, planner_mock):
        return PrepareRegionPreviewUseCase(inspector_mock, planner_mock)

    def test_preview_success(self, use_case, planner_mock):
        # Arrange
        region = TranslationRegion(id="r1", project_id="p1", page_id=1, selection_rect=Rect(10, 10, 50, 50), translated_text="Translation")
        
        # specs, issues
        mock_spec = Mock()
        mock_spec.target_rect = Rect(10, 10, 50, 50)
        mock_spec.background_rgb = (255, 255, 255)
        mock_spec.blocks = ()
        planner_mock.plan_regions.return_value = ([mock_spec], [])
        
        # Act
        result = use_case.execute("fake_path.pdf", region, [region])
        
        # Assert
        assert result is not None
        assert result.overlay_rect == Rect(10, 10, 50, 50)
        assert result.background_rgb == (255, 255, 255)

    def test_preview_failure_returns_none(self, use_case, planner_mock):
        # Arrange
        region = TranslationRegion(id="r1", project_id="p1", page_id=1, selection_rect=Rect(10, 10, 50, 50), translated_text="Translation")
        
        # specs, issues -> empty specs means failure to plan
        planner_mock.plan_regions.return_value = ([], [PreflightIssue(PreflightIssueCode.OVERFLOW, PreflightSeverity.WARNING)])
        
        # Act
        result = use_case.execute("fake_path.pdf", region, [region])
        
        # Assert
        assert result is None
