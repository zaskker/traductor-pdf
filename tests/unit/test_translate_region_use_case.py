from unittest.mock import MagicMock
from src.domain.models.project import Project
from datetime import datetime, UTC
import pytest

from src.application.services.prompt_builder import TranslationPromptBuilder
from src.application.services.token_protector import TokenProtector
from src.application.use_cases.translate_region import (
    TranslateRegionRequest,
    TranslateRegionUseCase,
)
from src.domain.interfaces.translation import InvalidTranslationResultError, TokenRestorationError
from src.domain.models.enums import RegionStatus
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.extraction import SourceFragment, FragmentGranularity
from src.infrastructure.translation.fake_engine import FakeTranslationEngine


class DummyRepo:
    def __init__(self):
        self.regions = {}

    def get(self, rid):
        return self.regions.get(rid)

    def save(self, region):
        self.regions[region.id] = region


@pytest.fixture
def repo():
    return DummyRepo()


@pytest.fixture
def engine():
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola", "Apple": "Manzana"}
    return engine


@pytest.fixture
def use_case(engine, repo):
    return TranslateRegionUseCase(
        engine=engine,
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder(),
    )


@pytest.fixture
def region(repo):
    r = TranslationRegion(
        id="reg_1",
        project_id="proj_1",
        page_id=1,
        selection_rect=Rect(0, 0, 10, 10),
        source_text="Hello",
        status=RegionStatus.PENDING,
    )
    repo.save(r)
    return r


def test_translate_pending_to_translated(use_case, repo, region):
    req = TranslateRegionRequest("reg_1", "en", "es", False)
    old_r, new_r = use_case.execute(req)

    assert old_r.status == RegionStatus.PENDING
    assert old_r.translated_text == ""

    assert new_r.status == RegionStatus.TRANSLATED
    assert new_r.translated_text == "Hola"
    assert new_r.translation_engine == "FakeEngine"


def test_translate_retranslated_A_to_B(use_case, repo, region):
    region.source_text = "Apple"
    region.translated_text = "Pineapple"
    region.status = RegionStatus.TRANSLATED

    req = TranslateRegionRequest("reg_1", "en", "es", False)
    old_r, new_r = use_case.execute(req)

    assert old_r.translated_text == "Pineapple"
    assert new_r.translated_text == "Manzana"
    assert new_r.status == RegionStatus.TRANSLATED


def test_translate_locked_rejected(use_case, region):
    req = TranslateRegionRequest("reg_1", "en", "es", True)
    with pytest.raises(ValueError, match="locked"):
        use_case.execute(req)


def test_translate_empty_source_behavior(use_case, repo, region):
    region.source_text = "   "
    req = TranslateRegionRequest("reg_1", "en", "es", False)
    with pytest.raises(ValueError, match="empty"):
        use_case.execute(req)


def test_translate_empty_engine_result(use_case, repo, region, engine):
    region.source_text = "EmptyTest"
    engine.configured_mapping["EmptyTest"] = "   "
    req = TranslateRegionRequest("reg_1", "en", "es", False)
    with pytest.raises(
        InvalidTranslationResultError,
        match="Engine returned an empty translation.",
    ):
        use_case.execute(req)


def test_translate_token_restore_failure(use_case, repo, region, engine):
    # Setup token mapping that doesn't include the restored token
    region.source_text = "Check this URL: https://example.com"
    # The protected text will be "Check this URL: [[TP_0001]]"
    # But the mock engine will return something else without the token
    engine.configured_mapping["Check this URL: [[TP_0001]]"] = "Mira esto: nada"

    req = TranslateRegionRequest("reg_1", "en", "es", False)
    with pytest.raises(TokenRestorationError):
        use_case.execute(req)


def test_structured_translate_success(use_case, repo, region, engine):
    f1 = SourceFragment("Block 1", Rect(0,0,10,10), FragmentGranularity.SPAN, 0, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    f2 = SourceFragment("Block 2", Rect(0,20,10,30), FragmentGranularity.SPAN, 1, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    region.source_fragments = (f1, f2)
    region.source_text = "Block 1\n\nBlock 2"

    engine.configured_mapping["[[BLOCK_0000]]\nBlock 1\n\n[[BLOCK_0001]]\nBlock 2"] = "[[BLOCK_0000]]\nBloque 1\n\n[[BLOCK_0001]]\nBloque 2"

    req = TranslateRegionRequest("reg_1", "en", "es", False)
    old_r, new_r = use_case.execute(req)
    
    assert new_r.translated_text == "Bloque 1\n\nBloque 2"


def test_structured_translate_marker_rejection(use_case, repo, region, engine):
    f1 = SourceFragment("B1", Rect(0,0,10,10), FragmentGranularity.SPAN, 0, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    f2 = SourceFragment("B2", Rect(0,20,10,30), FragmentGranularity.SPAN, 1, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    region.source_fragments = (f1, f2)
    region.source_text = "B1\n\nB2"

    engine.configured_mapping["[[BLOCK_0000]]\nB1\n\n[[BLOCK_0001]]\nB2"] = "[[BLOCK_0000]]\nB1"

    req = TranslateRegionRequest("reg_1", "en", "es", False)
    with pytest.raises(InvalidTranslationResultError, match="Structural marker mismatch"):
        use_case.execute(req)


def test_structured_translate_reordered_markers(use_case, repo, region, engine):
    f1 = SourceFragment("B1", Rect(0,0,10,10), FragmentGranularity.SPAN, 0, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    f2 = SourceFragment("B2", Rect(0,20,10,30), FragmentGranularity.SPAN, 1, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    region.source_fragments = (f1, f2)
    region.source_text = "B1\n\nB2"

    engine.configured_mapping["[[BLOCK_0000]]\nB1\n\n[[BLOCK_0001]]\nB2"] = "[[BLOCK_0001]]\nB2\n\n[[BLOCK_0000]]\nB1"

    req = TranslateRegionRequest("reg_1", "en", "es", False)
    with pytest.raises(InvalidTranslationResultError, match="Structural marker mismatch"):
        use_case.execute(req)


def test_structured_translate_empty_block_rejection(use_case, repo, region, engine):
    f1 = SourceFragment("B1", Rect(0,0,10,10), FragmentGranularity.SPAN, 0, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    f2 = SourceFragment("B2", Rect(0,20,10,30), FragmentGranularity.SPAN, 1, 0, 0, "font", 12, "#000000", 0, False, False, False, False)
    region.source_fragments = (f1, f2)
    region.source_text = "B1\n\nB2"

    engine.configured_mapping["[[BLOCK_0000]]\nB1\n\n[[BLOCK_0001]]\nB2"] = "[[BLOCK_0000]]\n  \n\n[[BLOCK_0001]]\nB2"

    req = TranslateRegionRequest("reg_1", "en", "es", False)
    with pytest.raises(InvalidTranslationResultError, match="empty in translation"):
        use_case.execute(req)

