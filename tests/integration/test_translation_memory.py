import pytest
import sqlite3
import os
from datetime import UTC, datetime
from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.repository import SqliteProjectRepository, SqliteTranslationRegionRepository, SqliteUnitOfWork
from src.infrastructure.persistence.translation_memory_repository import SqliteTranslationMemoryRepository
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion, RegionStatus, ReviewStatus
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.extraction import SourceFragment, FragmentGranularity
from src.application.use_cases.approve_translation import ApproveTranslationUseCase
from src.application.use_cases.translate_region import TranslateRegionUseCase, TranslateRegionRequest

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")

@pytest.fixture
def db(db_path):
    database = Database(db_path)
    database.init_schema()
    yield database
    database.close()

@pytest.fixture
def setup_data(db):
    uow = SqliteUnitOfWork(db)
    proj_repo = SqliteProjectRepository(db)
    p = Project(id="p1", name="Test", pdf_path="x.pdf", pdf_sha256="sha", pdf_size=10, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    proj_repo.save(p)
    return uow, p

def create_region(r_id, text, blocks):
    r = TranslationRegion(id=r_id, project_id="p1", page_id=1, selection_rect=Rect(0,0,10,10), source_fragments=tuple(blocks), source_text=text)
    return r

# MEM01 to MEM30 placeholders
# I will implement all of them here...

from unittest.mock import MagicMock
from src.domain.interfaces.translation import InvalidTranslationResultError

def get_base_fragment(text, block_index=0, line_index=0, span_index=0):
    return SourceFragment(text=text, bbox=Rect(0,0,10,10), granularity=FragmentGranularity.SPAN, block_index=block_index, line_index=line_index, span_index=span_index, raw_font_name="Arial", font_size=10, font_color="#000", font_flags_raw=0, is_bold=False, is_italic=False, is_serif=False, is_monospace=False)

def test_mem01_manual_approval_feeds_memory(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello", [get_base_fragment("Hello")])
    r.translated_text = "Hola"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "Hola"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    uc = ApproveTranslationUseCase(uow)
    uc.execute("r1", 1)
    
    # Check memory
    entries = uow.translation_memory_repository.get_by_project_and_hash("p1", "es", "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969")
    assert len(entries) == 1
    assert entries[0].target_text == "Hola"
    assert entries[0].original_translation_engine == "MANUAL"

def test_mem21_structural_change_reapproval(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello World", [get_base_fragment("Hello", 0), get_base_fragment("World", 1)])
    r.translated_text = "Hola\nMundo"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "Hola"}, {"id": "b2", "source_block_index": 1, "text": "Mundo"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    uc = ApproveTranslationUseCase(uow)
    uc.execute("r1", 1)
    
    # User edits, structural change -> 1 block now
    r = uow.region_repository.get("r1")
    r.translated_text = "Hola Mundo"
    r.translated_blocks = [{"id": "b3", "source_block_index": 0, "text": "Hola Mundo"}] # block 1 lost
    r.translation_revision = 2
    
    r.reviewed_translation_revision = 2
    uow.region_repository.save(r)
    
    uc.execute("r1", 2)
    
    # Check memory - old block 1 should be gone!
    with uow.db.transaction() as conn:
        c = conn.execute("SELECT count(*) FROM translation_memory_entry WHERE region_id='r1'")
        assert c.fetchone()[0] == 1 # Only 1 block now!

def test_mem22_atomic_failure_reverts_approval(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello", [get_base_fragment("Hello")])
    r.translated_text = "Hola"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "Hola"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    original_upsert = SqliteTranslationMemoryRepository.upsert
    def failing_upsert(self, *args, **kwargs):
        raise Exception("DB Disk Full")
    SqliteTranslationMemoryRepository.upsert = failing_upsert
    
    uc = ApproveTranslationUseCase(uow)
    import pytest
    try:
        with pytest.raises(Exception):

            uc.execute("r1", 1)
    finally:
        SqliteTranslationMemoryRepository.upsert = original_upsert
        
    # Region should NOT be approved
    r_check = uow.region_repository.get("r1")
    assert r_check.review_status == ReviewStatus.REVIEWED
    assert r_check.approved_translation_revision is None

def test_mem23_exact_reuse_case_sensitive(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "US", [get_base_fragment("US")])
    r.translated_text = "EEUU"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "EEUU"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.translation_options = {"target_language": "es"}
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    ApproveTranslationUseCase(uow).execute("r1", 1)
    
    # Now translate "us"
    r2 = create_region("r2", "us", [get_base_fragment("us")])
    r2.translation_options = {"target_language": "es"}
    uow.region_repository.save(r2)
    
    engine = MagicMock()
    engine.translate.return_value = MagicMock(translated_text="nosotros", engine_name="ollama", model_name="llama3")
    proj_repo = MagicMock()
    proj_repo.get.return_value = proj
    prompt_builder = MagicMock()
    prompt_builder.build_system_prompt.return_value = ""
    prompt_builder.build_user_prompt.return_value = ""
    token_protector = MagicMock()
    token_protector.protect.return_value = MagicMock(text="us")
    token_protector.restore.return_value = "nosotros"
    
    uc = TranslateRegionUseCase(engine, uow.region_repository, proj_repo, MagicMock(), token_protector, prompt_builder, uow.translation_memory_repository)
    _, new_r2 = uc.execute(TranslateRegionRequest("r2", "en", "es", False))
    
    # Should NOT use exact reuse because "us" != "US" (case sensitive for hash!)
    assert new_r2.translation_engine == "ollama"
    assert new_r2.translated_text == "nosotros"

def test_mem26_manual_edit_no_source_mapping(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello", [get_base_fragment("Hello")])
    r.translated_text = "Hola"
    r.translated_blocks = [{"id": "b1", "source_block_index": -1, "text": "Hola"}] # lost mapping
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    uc = ApproveTranslationUseCase(uow)
    uc.execute("r1", 1)
    
    with uow.db.transaction() as conn:
        c = conn.execute("SELECT count(*) FROM translation_memory_entry WHERE region_id='r1'")
        assert c.fetchone()[0] == 0

def test_mem27_delete_project_cascade(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello", [get_base_fragment("Hello")])
    r.translated_text = "Hola"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "Hola"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    uc = ApproveTranslationUseCase(uow)
    uc.execute("r1", 1)
    
    proj_repo = SqliteProjectRepository(uow.db)
    with uow.db.transaction() as conn:
        conn.execute("DELETE FROM project WHERE id='p1'")
        
    with uow.db.transaction() as conn:
        c = conn.execute("SELECT count(*) FROM translation_memory_entry")
        assert c.fetchone()[0] == 0

def test_mem28_delete_region_conserves_memory(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello", [get_base_fragment("Hello")])
    r.translated_text = "Hola"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "Hola"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    uc = ApproveTranslationUseCase(uow)
    uc.execute("r1", 1)
    
    uow.region_repository.delete("r1")
    
    with uow.db.transaction() as conn:
        c = conn.execute("SELECT count(*) FROM translation_memory_entry")
        assert c.fetchone()[0] == 1

def test_mem29_corpus_exact_unreviewed(setup_data):
    uow, proj = setup_data
    r = create_region("r1", "Hello", [get_base_fragment("Hello")])
    r.translated_text = "Hola"
    r.translated_blocks = [{"id": "b1", "source_block_index": 0, "text": "Hola"}]
    r.translation_revision = 1
    
    r.reviewed_translation_revision = 1
    r.translation_options = {"target_language": "es"}
    r.is_manually_edited = True
    uow.region_repository.save(r)
    
    ApproveTranslationUseCase(uow).execute("r1", 1)
    
    r2 = create_region("r2", "Hello", [get_base_fragment("Hello")])
    r2.translation_options = {"target_language": "es"}
    uow.region_repository.save(r2)
    
    proj_repo = SqliteProjectRepository(uow.db)
    uc = TranslateRegionUseCase(MagicMock(), uow.region_repository, proj_repo, MagicMock(), MagicMock(), MagicMock(), uow.translation_memory_repository)
    _, new_r2 = uc.execute(TranslateRegionRequest("r2", "en", "es", False))
    
    assert new_r2.translation_engine == "MANUAL"
    assert new_r2.review_status == ReviewStatus.UNREVIEWED
    assert new_r2.translation_revision == 1
    assert new_r2.translated_text == "Hola"
