import pytest

from src.domain.interfaces.translation import InvalidTranslationResultError, TranslationResult


def test_translation_result_valid():
    result = TranslationResult(
        translated_text="Hola",
        engine_name="FakeEngine",
        model_name="FakeModel",
    )
    assert result.translated_text == "Hola"
    assert result.engine_name == "FakeEngine"
    assert result.model_name == "FakeModel"


def test_translation_result_empty_engine_rejected():
    with pytest.raises(InvalidTranslationResultError, match="engine_name cannot be empty"):
        TranslationResult(translated_text="Hola", engine_name="   ", model_name="FakeModel")


def test_translation_result_empty_model_name_allowed_for_fake():
    result = TranslationResult(translated_text="Hola", engine_name="FakeEngine", model_name="")
    assert result.model_name == ""
