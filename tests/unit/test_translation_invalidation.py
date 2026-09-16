from datetime import UTC

import pytest

from src.application.use_cases.move_resize_region import MoveResizeRegionUseCase
from src.domain.models.enums import ExtractionMethod, RegionStatus
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import (
    FragmentGranularity,
    SourceFragment,
    TextExtractionResult,
)
from src.domain.value_objects.geometry import Rect
from src.infrastructure.translation.fake_engine import FakeTranslationEngine


class DummyExtractionService:
    def __init__(self):
        self.result = TextExtractionResult(
            page_number=1,
            selection_rect=Rect(0, 0, 10, 10),
            text="Hello",
            fragments=(
                SourceFragment(
                    "Hello",
                    Rect(0, 0, 10, 10),
                    FragmentGranularity.SPAN,
                    0,
                    0,
                    0,
                    "Arial",
                    10.0,
                    "#000000",
                    0,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
            source_bbox=Rect(0, 0, 10, 10),
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            warnings=(),
        )

    def extract_from_selection(self, selection):
        return self.result


@pytest.fixture
def use_case():
    return MoveResizeRegionUseCase(DummyExtractionService())


@pytest.fixture
def project():
    from datetime import datetime

    return Project(
        id="proj_1",
        name="p",
        pdf_path="f.pdf",
        pdf_sha256="123",
        pdf_size=10,
        pdf_page_count=1,
        last_viewed_page=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def fake_engine():
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola"}
    return engine


@pytest.fixture
def old_region():
    return TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        translated_text="Hola",
        status=RegionStatus.TRANSLATED,
    )


def test_move_preserves_translation_if_exact_match(use_case, project, old_region):
    # Dummy service returns "Hello", exact match
    new_r = use_case.execute(project, old_region, Rect(5, 5, 15, 15))
    assert new_r.translated_text == "Hola"
    assert new_r.status == RegionStatus.TRANSLATED


def test_move_invalidates_if_whitespace_diff(use_case, project, old_region):
    use_case.extraction_service.result = TextExtractionResult(
        page_number=1,
        selection_rect=Rect(0, 0, 10, 10),
        text="Hello ",
        fragments=use_case.extraction_service.result.fragments,
        source_bbox=Rect(0, 0, 10, 10),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        warnings=(),
    )
    new_r = use_case.execute(project, old_region, Rect(5, 5, 15, 15))
    assert new_r.translated_text == ""
    assert new_r.status == RegionStatus.PENDING


def test_move_invalidates_if_line_break_diff(use_case, project, old_region):
    use_case.extraction_service.result = TextExtractionResult(
        page_number=1,
        selection_rect=Rect(0, 0, 10, 10),
        text="Hel\nlo",
        fragments=use_case.extraction_service.result.fragments,
        source_bbox=Rect(0, 0, 10, 10),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        warnings=(),
    )
    new_r = use_case.execute(project, old_region, Rect(5, 5, 15, 15))
    assert new_r.translated_text == ""
    assert new_r.status == RegionStatus.PENDING
