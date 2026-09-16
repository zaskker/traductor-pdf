import pytest
from src.domain.models.region import TranslationRegion, RegionStatus, ReviewStatus
from src.domain.interfaces.translation import TranslationNotReviewedError, StaleTranslationRevisionError
from src.domain.value_objects.geometry import Rect
from src.application.use_cases.mark_translation_reviewed import MarkTranslationReviewedUseCase
from src.application.use_cases.approve_translation import ApproveTranslationUseCase

class DummyUoW:
    def __init__(self, region):
        self.region = region
        self.region_repository = self
        self.translation_memory_repository = self
    
    def __enter__(self): return self
    def __exit__(self, *args): pass
    
    def get(self, r_id): return self.region
    def save(self, r): pass
    def delete_for_region(self, r_id): pass
    def upsert(self, entry): pass

from src.application.use_cases.translate_region import TranslateRegionUseCase, TranslateRegionRequest


def create_region(status=RegionStatus.TRANSLATED, rev=1, rev_rev=None, app_rev=None):
    r = TranslationRegion("r1", "p1", 1, Rect(0,0,10,10), source_fragments=())
    r.status = status
    r.translation_revision = rev
    r.reviewed_translation_revision = rev_rev
    r.approved_translation_revision = app_rev
    r.source_text = "SRC"
    r.translated_text = "OK"
    return r

# REV01 Sin traducción -> UNTRANSLATED.
def test_rev01_untranslated():
    r = create_region(status=RegionStatus.PENDING, rev=None)
    assert r.review_status == ReviewStatus.UNTRANSLATED

# REV02 Traducción nueva -> UNREVIEWED.
def test_rev02_new_translation():
    r = create_region(rev=1)
    assert r.review_status == ReviewStatus.UNREVIEWED

# REV03 Mark Reviewed -> REVIEWED.
def test_rev03_mark_reviewed():
    r = create_region(rev=1)
    
    
        
    uc = MarkTranslationReviewedUseCase(DummyUoW(r))
    _, new_r = uc.execute("r1", 1)
    assert new_r.review_status == ReviewStatus.REVIEWED
    assert new_r.reviewed_translation_revision == 1

# REV04 Reviewed -> Approved.
def test_rev04_approve_reviewed():
    r = create_region(rev=1, rev_rev=1)
    
    uc = ApproveTranslationUseCase(DummyUoW(r))
    _, new_r = uc.execute("r1", 1)
    assert new_r.review_status == ReviewStatus.APPROVED
    assert new_r.approved_translation_revision == 1

# REV05 aprobar sin review -> TranslationNotReviewedError.
def test_rev05_approve_unreviewed():
    r = create_region(rev=1)
    
    uc = ApproveTranslationUseCase(DummyUoW(r))
    with pytest.raises(TranslationNotReviewedError):
        uc.execute("r1", 1)

# REV06 revision stale -> StaleTranslationRevisionError.
def test_rev06_stale_revision():
    r = create_region(rev=2)
    
    
        
    uc = MarkTranslationReviewedUseCase(DummyUoW(r))
    with pytest.raises(StaleTranslationRevisionError):
        uc.execute("r1", 1)
        
    uc2 = ApproveTranslationUseCase(DummyUoW(r))
    with pytest.raises(StaleTranslationRevisionError):
        uc2.execute("r1", 1)

# REV07 edición de approved -> UNREVIEWED.
def test_rev07_edit_approved():
    r = create_region(rev=1, rev_rev=1, app_rev=1)
    assert r.review_status == ReviewStatus.APPROVED
    
    r.translated_text = "Edited"
    r.translation_revision = 2
    # Simulation of edit: it resets revs since it's a new revision
    
    assert r.review_status == ReviewStatus.UNREVIEWED

# REV08 retranslación válida de approved -> UNREVIEWED.
def test_rev08_retranslation_approved_unreviewed():
    r = create_region(rev=1, rev_rev=1, app_rev=1)
    
    class DummyEngine:
        def translate(self, **kwargs): return MagicMock(translated_text="New")
        
    
        
    class DummyProject:
        glossary_id = None
        active_glossary_id = None
        def get(self, id): return self
        
    class DummyGlossaryRepo: pass
    from unittest.mock import MagicMock
    token_protector = MagicMock()
    token_protector.protect.return_value = MagicMock(text='protected')
    token_protector.unprotect.return_value = 'unprotected'
    prompt_builder = MagicMock()
    prompt_builder.build_system_prompt.return_value = 'sys'
    prompt_builder.build_user_prompt.return_value = 'usr'

    uc = TranslateRegionUseCase(DummyEngine(), DummyUoW(r), DummyProject(), DummyGlossaryRepo(), token_protector, prompt_builder)
    _, new_r = uc.execute(TranslateRegionRequest(region_id="r1", source_language="en", target_language="es", project_locked=False))
    
    assert new_r.review_status == ReviewStatus.UNREVIEWED
    assert new_r.translation_revision == 2
    assert new_r.approved_translation_revision == 1

# REV09 retranslación fallida conserva APPROVED.
def test_rev09_failed_retranslation_conserves_approved():
    r = create_region(rev=1, rev_rev=1, app_rev=1)
    
    class DummyEngine:
        def translate(self, **kwargs): raise Exception("Network Error")
        
    
        
    class DummyProject:
        glossary_id = None
        active_glossary_id = None
        def get(self, id): return self
        
    class DummyGlossaryRepo: pass
    from unittest.mock import MagicMock
    token_protector = MagicMock()
    token_protector.protect.return_value = MagicMock(text='protected')
    token_protector.unprotect.return_value = 'unprotected'
    prompt_builder = MagicMock()
    prompt_builder.build_system_prompt.return_value = 'sys'
    prompt_builder.build_user_prompt.return_value = 'usr'

    uc = TranslateRegionUseCase(DummyEngine(), DummyUoW(r), DummyProject(), DummyGlossaryRepo(), token_protector, prompt_builder)
    try:
        uc.execute(TranslateRegionRequest(region_id="r1"))
    except:
        pass
    
    assert r.review_status == ReviewStatus.APPROVED
    assert r.translation_revision == 1

# REV10 GlossaryMismatch conserva APPROVED.
def test_rev10_glossary_mismatch_conserves_approved():
    r = create_region(rev=1, rev_rev=1, app_rev=1)
    r.glossary_revision = 1
    
    assert r.review_status == ReviewStatus.APPROVED
    r.glossary_revision = 2
    
    assert r.review_status == ReviewStatus.APPROVED
