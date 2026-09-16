from unittest.mock import MagicMock
from src.domain.models.project import Project
from datetime import datetime, UTC
import sqlite3
import pytest
from src.domain.models.region import TranslationRegion
from src.domain.models.enums import RegionStatus, RegionType, ExtractionMethod, FitStatus
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.extraction import SourceFragment, FragmentGranularity
from src.application.use_cases.translate_region import TranslateRegionUseCase, TranslateRegionRequest
from src.application.use_cases.edit_translation import EditTranslationUseCase
from src.infrastructure.translation.fake_engine import FakeTranslationEngine
from src.application.services.token_protector import TokenProtector
from src.application.services.prompt_builder import TranslationPromptBuilder
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteTranslationRegionRepository

@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test_meta.db"
    db = Database(str(db_path))
    db.init_schema()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at) "
            "VALUES ('proj-1', 'Test', 'test.pdf', 'abc', 100, 1, 0, '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
        )
    repository = SqliteTranslationRegionRepository(db)
    yield repository
    db.close()

def _create_basic_region(repo, region_id="reg-meta"):
    frag = SourceFragment(
        text="Hello",
        bbox=Rect(0, 0, 100, 10),
        granularity=FragmentGranularity.SPAN,
        block_index=0,
        line_index=0,
        span_index=0,
        raw_font_name="Arial",
        font_size=12.0,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False
    )
    region = TranslationRegion(
        id=region_id,
        project_id="proj-1",
        page_id=0,
        selection_rect=Rect(0, 0, 100, 10),
        source_fragments=[frag],
        source_text="Hello",
        status=RegionStatus.PENDING
    )
    repo.save(region)
    return region

def test_META01_META02_engine_model_persists(repo):
    _create_basic_region(repo)
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola"}
    uc = TranslateRegionUseCase(
        engine=engine,
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, new = uc.execute(TranslateRegionRequest("reg-meta", "en", "es", False))
    repo.save(new)
    
    restored = repo.get("reg-meta")
    assert restored.translation_engine == "FakeEngine"
    assert restored.translation_model == "FakeModel"

def test_META03_META04_options_and_prompt_roundtrip(repo):
    _create_basic_region(repo)
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola"}
    uc = TranslateRegionUseCase(
        engine=engine,
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, new = uc.execute(TranslateRegionRequest("reg-meta", "en", "es", False))
    repo.save(new)
    
    restored = repo.get("reg-meta")
    assert restored.prompt_template_version == "v1"
    assert restored.translation_options is not None
    assert restored.translation_options["target_language"] == "es"
    assert restored.translation_options["schema_version"] == 1

def test_META05_META06_glossary_roundtrip(repo):
    # Simulate saving a region with glossary explicitly
    region = _create_basic_region(repo)
    region.glossary_id = "glos-1"
    region.glossary_revision = 5
    repo.save(region)
    
    restored = repo.get("reg-meta")
    assert restored.glossary_id == "glos-1"
    assert restored.glossary_revision == 5
    
    # And None legacy
    region.glossary_id = None
    region.glossary_revision = None
    repo.save(region)
    
    restored_none = repo.get("reg-meta")
    assert restored_none.glossary_id is None
    assert restored_none.glossary_revision is None

def test_META07_META10_META11_translation_revision(repo):
    _create_basic_region(repo)
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola"}
    uc = TranslateRegionUseCase(
        engine=engine,
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    # 1. Primera traduccion
    _, trans1 = uc.execute(TranslateRegionRequest("reg-meta", "en", "es", False))
    assert trans1.translation_revision == 1
    repo.save(trans1)
    
    # Restart no altera
    restored = repo.get("reg-meta")
    assert restored.translation_revision == 1
    
    # 2. Retraduccion
    _, trans2 = uc.execute(TranslateRegionRequest("reg-meta", "en", "es", False))
    assert trans2.translation_revision == 2
    repo.save(trans2)
    
    # 3. Edicion manual
    uc_edit = EditTranslationUseCase(repo)
    _, trans_edit = uc_edit.execute("reg-meta", "Hola manual")
    assert trans_edit.translation_revision == 3
    assert trans_edit.is_manually_edited is True
    repo.save(trans_edit)
    
    restored_edit = repo.get("reg-meta")
    assert restored_edit.translation_revision == 3

def test_META08_META09_error_and_cancel_do_not_increment(repo):
    _create_basic_region(repo)
    engine = FakeTranslationEngine()
    engine.configured_mapping = {"Hello": "Hola"}
    uc = TranslateRegionUseCase(
        engine=engine,
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, trans1 = uc.execute(TranslateRegionRequest("reg-meta", "en", "es", False))
    assert trans1.translation_revision == 1
    repo.save(trans1)
    
    # Error will raise exception, no new region snapshot returned
    engine.should_fail = True
    with pytest.raises(Exception):
        uc.execute(TranslateRegionRequest("reg-meta", "en", "es", False))
        
    restored = repo.get("reg-meta")
    assert restored.translation_revision == 1  # Intacto
