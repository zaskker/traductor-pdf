from src.domain.value_objects.translation import TranslationRequest
from src.infrastructure.translation.fake_engine import FakeTranslationEngine


def test_translation_request_creation():
    req = TranslationRequest(text="Hello World", protected_tokens={"{{T_0}}": "World"})
    assert req.text == "Hello World"
    assert req.source_language == "en"
    assert req.target_language == "es"
    assert req.protected_tokens["{{T_0}}"] == "World"


def test_fake_translation_engine():
    engine = FakeTranslationEngine()
    res = engine.translate("System rules", "<TRANSLATION_SOURCE>\nHello\n</TRANSLATION_SOURCE>")
    assert res.translated_text == "[TRANSLATED] Hello"
    assert res.engine_name == "FakeEngine"
