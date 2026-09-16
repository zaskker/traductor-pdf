from unittest.mock import MagicMock
from src.domain.models.project import Project
from datetime import datetime, UTC
import sqlite3
import pytest
import uuid
import copy
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
    db_path = tmp_path / "test.db"
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

def _create_region_with_blocks(repo, region_id="reg-1", num_blocks=2):
    fragments = []
    text_parts = []
    for i in range(num_blocks):
        frag = SourceFragment(
            text=f"Block {i}",
            bbox=Rect(0, i*10, 100, (i+1)*10),
            granularity=FragmentGranularity.SPAN,
            block_index=i,
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
        fragments.append(frag)
        text_parts.append(f"Block {i}")
        
    region = TranslationRegion(
        id=region_id,
        project_id="proj-1",
        page_id=0,
        selection_rect=Rect(0, 0, 100, num_blocks*10),
        source_fragments=fragments,
        source_text="\n\n".join(text_parts),
        status=RegionStatus.PENDING
    )
    repo.save(region)
    return region

def test_ID01_block_ids_generated(repo):
    _create_region_with_blocks(repo, "reg-1", 2)
    uc = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    req = TranslateRegionRequest("reg-1", "en", "es", False)
    old, new = uc.execute(req)
    
    assert new.translated_blocks is not None
    assert len(new.translated_blocks) == 2
    assert new.translated_blocks[0]["id"] is not None
    assert new.translated_blocks[1]["id"] is not None
    assert new.translated_blocks[0]["source_block_index"] == 0
    assert new.translated_blocks[1]["source_block_index"] == 1
    assert new.translated_blocks[0]["id"] != new.translated_blocks[1]["id"]

def test_ID02_restart_maintains_ids(repo):
    _create_region_with_blocks(repo, "reg-1", 2)
    uc = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, new = uc.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    repo.save(new)
    
    # Simulate restart by reading again
    restored = repo.get("reg-1")
    assert restored.translated_blocks == new.translated_blocks

def test_ID03_stable_order(repo):
    _create_region_with_blocks(repo, "reg-1", 3)
    uc = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, new = uc.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    
    # Order should strictly match source_block_index
    assert new.translated_blocks[0]["source_block_index"] == 0
    assert new.translated_blocks[1]["source_block_index"] == 1
    assert new.translated_blocks[2]["source_block_index"] == 2

def test_ID04_manual_edit_does_not_change_ids_if_structure_preserved(repo):
    _create_region_with_blocks(repo, "reg-1", 2)
    uc_trans = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    _, trans_new = uc_trans.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    repo.save(trans_new)
    
    uc_edit = EditTranslationUseCase(repo)
    # Edit preserving 2 blocks
    new_text = "Edited Block 0\n\nEdited Block 1"
    old, edit_new = uc_edit.execute("reg-1", new_text)
    
    assert len(edit_new.translated_blocks) == 2
    assert edit_new.translated_blocks[0]["id"] == trans_new.translated_blocks[0]["id"]
    assert edit_new.translated_blocks[1]["id"] == trans_new.translated_blocks[1]["id"]
    
def test_ID04_manual_edit_changes_ids_if_structure_broken(repo):
    _create_region_with_blocks(repo, "reg-1", 2)
    uc_trans = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    _, trans_new = uc_trans.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    repo.save(trans_new)
    
    uc_edit = EditTranslationUseCase(repo)
    # Edit merging blocks (now 1 block)
    new_text = "Edited Block 0 and 1"
    old, edit_new = uc_edit.execute("reg-1", new_text)
    
    assert len(edit_new.translated_blocks) == 1
    assert edit_new.translated_blocks[0]["id"] != trans_new.translated_blocks[0]["id"]
    assert edit_new.translated_blocks[0]["id"] != trans_new.translated_blocks[1]["id"]
    assert edit_new.translated_blocks[0]["source_block_index"] == -1  # Cannot map 1:1

def test_ID05_retranslation_maintains_ids(repo):
    _create_region_with_blocks(repo, "reg-1", 2)
    uc = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, trans1 = uc.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    repo.save(trans1)
    
    # Retranslate
    _, trans2 = uc.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    
    assert len(trans2.translated_blocks) == 2
    assert trans2.translated_blocks[0]["id"] == trans1.translated_blocks[0]["id"]
    assert trans2.translated_blocks[1]["id"] == trans1.translated_blocks[1]["id"]

def test_ID06_different_regions_do_not_collide(repo):
    _create_region_with_blocks(repo, "reg-1", 2)
    _create_region_with_blocks(repo, "reg-2", 2)
    
    uc = TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=repo,
        project_repository=MagicMock(get=lambda pid: Project(id=pid, name="test", pdf_path="test", pdf_sha256="sha", pdf_size=100, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))), glossary_repository=MagicMock(), token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder()
    )
    
    _, trans1 = uc.execute(TranslateRegionRequest("reg-1", "en", "es", False))
    _, trans2 = uc.execute(TranslateRegionRequest("reg-2", "en", "es", False))
    
    ids1 = {b["id"] for b in trans1.translated_blocks}
    ids2 = {b["id"] for b in trans2.translated_blocks}
    
    assert ids1.isdisjoint(ids2)
