import pytest
from uuid import uuid4
from datetime import datetime, UTC
from src.application.use_cases.translate_region import TranslateRegionRequest, TranslateRegionUseCase
from src.domain.interfaces.translation import StructuralMarkerMismatchError
from src.application.dtos.translation_execution_config import TranslationExecutionConfig
from src.infrastructure.translation.fake_engine import FakeTranslationEngine
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import SourceFragment, FragmentGranularity
from src.domain.value_objects.geometry import Rect
from src.application.services.prompt_builder import TranslationPromptBuilder
from src.application.services.token_protector import TokenProtector

class MockRepository:
    def __init__(self):
        self.regions = {}
    def get(self, id):
        return self.regions.get(id)
    def save(self, r):
        self.regions[r.id] = r
    def get_by_page(self, p, pg): return list(self.regions.values())

class MockProjectRepo:
    def get(self, id): return None

@pytest.fixture
def use_case():
    return TranslateRegionUseCase(
        engine=FakeTranslationEngine(),
        repository=MockRepository(),
        project_repository=MockProjectRepo(),
        glossary_repository=None,
        token_protector=TokenProtector(),
        prompt_builder=TranslationPromptBuilder(),
        memory_repository=None
    )

@pytest.fixture
def sample_region():
    # 2 blocks to trigger structured mode
    f1 = SourceFragment(text="Block 0", bbox=Rect(0,0,10,10), granularity=FragmentGranularity.SPAN, block_index=0, line_index=0, span_index=0, raw_font_name="Arial", font_size=10, font_color="#000000", font_flags_raw=0, is_bold=False, is_italic=False, is_serif=False, is_monospace=False)
    f2 = SourceFragment(text="Block 1", bbox=Rect(0,20,10,30), granularity=FragmentGranularity.SPAN, block_index=1, line_index=1, span_index=0, raw_font_name="Arial", font_size=10, font_color="#000000", font_flags_raw=0, is_bold=False, is_italic=False, is_serif=False, is_monospace=False)
    r = TranslationRegion(
        id="r1", project_id="p1", page_id=0,
        selection_rect=Rect(0,0,10,30),
        source_fragments=[f1, f2],
        translated_text="",
        is_manually_edited=False
    )
    r.source_text = "Block 0\n\nBlock 1"
    r.updated_at = datetime.now(UTC)
    return r

def test_struct01_missing_marker(use_case, sample_region):
    # Setup
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0001]]\nTranslated 1",
        "[[BLOCK_0001]]\nTranslated 1" # Fails again on retry
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    with pytest.raises(StructuralMarkerMismatchError) as exc:
        use_case.execute(req)
        
    assert "Expected" in str(exc.value)
    assert use_case.engine.call_count == 2 # Attempt 1, Attempt 2

def test_struct02_retry_success(use_case, sample_region):
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0001]]\nTranslated 1", # Missing 0000 -> retry
        "[[BLOCK_0000]]\nTranslated 0\n\n[[BLOCK_0001]]\nTranslated 1" # Success
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    old_r, new_r = use_case.execute(req)
    assert new_r.translated_text == "Translated 0\n\nTranslated 1"
    assert use_case.engine.call_count == 2

def test_struct03_both_fail(use_case, sample_region):
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0001]]\nTranslated 1",
        "[[BLOCK_0001]]\nTranslated 1" 
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    with pytest.raises(StructuralMarkerMismatchError):
        use_case.execute(req)
    assert use_case.engine.call_count == 2

def test_struct04_duplicate_marker(use_case, sample_region):
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0000]]\n0\n\n[[BLOCK_0000]]\ndup\n\n[[BLOCK_0001]]\n1",
        "[[BLOCK_0000]]\n0\n\n[[BLOCK_0001]]\n1"
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    old_r, new_r = use_case.execute(req)
    assert use_case.engine.call_count == 2
    assert "0\n\n1" == new_r.translated_text

def test_struct05_unexpected_marker(use_case, sample_region):
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0000]]\n0\n\n[[BLOCK_0001]]\n1\n\n[[BLOCK_0002]]\n2",
        "[[BLOCK_0000]]\n0\n\n[[BLOCK_0001]]\n1"
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    old_r, new_r = use_case.execute(req)
    assert use_case.engine.call_count == 2

def test_struct06_wrong_order(use_case, sample_region):
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0001]]\n1\n\n[[BLOCK_0000]]\n0",
        "[[BLOCK_0000]]\n0\n\n[[BLOCK_0001]]\n1"
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    old_r, new_r = use_case.execute(req)
    assert use_case.engine.call_count == 2

def test_struct07_trivial_block(use_case, sample_region):
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0000]]\nBlock 0\n\n[[BLOCK_0001]]\nBlock 1"
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    old_r, new_r = use_case.execute(req)
    assert new_r.translated_text == "Block 0\n\nBlock 1"

def test_struct09_retry_success_revision(use_case, sample_region):
    sample_region.translation_revision = 1
    use_case.repository.save(sample_region)
    use_case.engine.responses = [
        "[[BLOCK_0001]]\nTranslated 1", 
        "[[BLOCK_0000]]\nTranslated 0\n\n[[BLOCK_0001]]\nTranslated 1" 
    ]
    req = TranslateRegionRequest(region_id="r1")
    
    old_r, new_r = use_case.execute(req)
    assert new_r.translation_revision == 2 # Incremented exactly once

def test_struct11_cancel_between_attempts(use_case, sample_region):
    use_case.repository.save(sample_region)
    
    # Custom engine to simulate cancellation by modifying the region while running
    class CancellingEngine(FakeTranslationEngine):
        def translate(self, system_prompt, user_prompt):
            if self.call_count == 0:
                # First attempt -> malformed
                self.call_count += 1
                # Simulate someone modified the region while this first attempt was running
                import time
                time.sleep(0.02)
                sample_region.updated_at = datetime.now(UTC)
                from src.domain.interfaces.translation import TranslationResult
                return TranslationResult(translated_text="[[BLOCK_0001]]\nTranslated 1", engine_name="fake", model_name="fake")
            elif self.call_count == 1:
                self.call_count += 1
                from src.domain.interfaces.translation import TranslationResult
                return TranslationResult(translated_text="[[BLOCK_0000]]\n0\n\n[[BLOCK_0001]]\n1", engine_name="fake", model_name="fake")
            return super().translate(system_prompt, user_prompt)
            
    engine = CancellingEngine()
    use_case.engine = engine
    
    req = TranslateRegionRequest(region_id="r1")
    
    with pytest.raises(ValueError) as exc:
        use_case.execute(req)
        
    assert "Region was modified or deleted" in str(exc.value)
    assert engine.call_count == 1 # Second attempt was aborted!
