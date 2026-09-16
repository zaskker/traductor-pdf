import pytest
import time
import threading
from datetime import datetime, UTC
from unittest.mock import MagicMock

from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.models.glossary import Glossary, GlossaryEntry
from src.domain.models.enums import RegionType, RegionStatus, ExtractionMethod, FitStatus
from src.domain.value_objects.geometry import Rect
from src.application.use_cases.translate_region import TranslateRegionUseCase, TranslateRegionRequest
from src.application.services.prompt_builder import TranslationPromptBuilder
from src.application.services.token_protector import TokenProtector
from src.infrastructure.translation.fake_engine import FakeTranslationEngine

def test_glossary_concurrent_snapshot():
    glossary = Glossary(id="g1", project_id="p1", name="Test Glossary", revision=4)
    glossary.add_entry(GlossaryEntry("e1", "apple", "manzana"))
    # Revision is now 5
    glossary.revision = 4  # Reset for test assumption
    
    # Setup Mocks and Repositories
    project_repo = MagicMock()
    project_repo.get.return_value = Project(id="p1", name="p", pdf_path="test", pdf_sha256="sha", pdf_size=1, pdf_page_count=1, last_viewed_page=1, created_at=datetime.now(UTC), updated_at=datetime.now(UTC), active_glossary_id="g1")
    
    glossary_repo = MagicMock()
    glossary_repo.get.return_value = glossary
    
    region_repo = MagicMock()
    
    class SlowFakeEngine(FakeTranslationEngine):
            def translate(self, system_prompt: str, user_prompt: str):
                glossary.add_entry(GlossaryEntry("e2", "banana", "banana"))
                assert glossary.revision == 5
                from src.domain.interfaces.translation import TranslationResult
                return TranslationResult(translated_text="Una manzana", engine_name="Fake", model_name="Fake")

    engine = SlowFakeEngine()
    engine.configured_mapping = {"apple": "manzana"}
    
    prompt_builder = TranslationPromptBuilder()
    token_protector = TokenProtector()
    
    use_case = TranslateRegionUseCase(engine, region_repo, project_repo, glossary_repo, token_protector, prompt_builder)
    
    region = TranslationRegion(
        id="r1", 
        project_id="p1", 
        page_id=1, 
        selection_rect=Rect(0,0,1,1),
        source_text="An apple", 
        translated_text="", 
        region_type=RegionType.TEXT_NATIVE, 
        status=RegionStatus.PENDING, 
        extraction_method=ExtractionMethod.NATIVE_TEXT, 
        fit_status=FitStatus.FIT, 
        created_at=datetime.now(UTC), 
        updated_at=datetime.now(UTC)
    )
    
    # 2. Iniciar traduccion
    # This will trigger the SlowFakeEngine, which modifies the glossary to revision 5 mid-flight
    region_repo.get.return_value = region
    request = TranslateRegionRequest(region_id="r1", source_language="en", target_language="es", project_locked=False)
    _, result_region = use_case.execute(request)
    
    # 5. Terminar request anterior
    # El resultado del request viejo tiene revision = 4.
    assert result_region.glossary_revision == 4
    # The actual glossary is at revision 5
    assert glossary.revision == 5
