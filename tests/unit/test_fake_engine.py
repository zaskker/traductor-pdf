import pytest

from src.domain.interfaces.translation import TranslationEngineError, TranslationTimeoutError
from src.infrastructure.translation.fake_engine import FakeTranslationEngine


def test_fake_engine_deterministic_output():
    engine = FakeTranslationEngine()
    res = engine.translate("System rules", "<TRANSLATION_SOURCE>\nHello\n</TRANSLATION_SOURCE>")

    assert res.translated_text == "[TRANSLATED] Hello"
    assert res.engine_name == "FakeEngine"
    assert engine.call_count == 1


def test_fake_engine_configured_mapping():
    engine = FakeTranslationEngine()
    engine.configured_mapping["Hello"] = "Hola"

    result = engine.translate("System", "<TRANSLATION_SOURCE>\nHello\n</TRANSLATION_SOURCE>")
    assert result.translated_text == "Hola"
    assert engine.call_count == 1


def test_fake_engine_failure():
    engine = FakeTranslationEngine()
    engine.should_fail = True

    with pytest.raises(TranslationEngineError, match="Fake engine failure"):
        engine.translate("Sys", "Hello")

    assert engine.call_count == 1


def test_fake_engine_timeout():
    engine = FakeTranslationEngine()
    engine.should_timeout = True

    with pytest.raises(TranslationTimeoutError, match="Fake timeout"):
        engine.translate("Sys", "Hello")

    assert engine.call_count == 1
