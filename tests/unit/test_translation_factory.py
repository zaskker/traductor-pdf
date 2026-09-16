import pytest

from src.composition.translation import TranslationConfigurationError, create_translation_engine
from src.infrastructure.translation.config import OllamaConfig
from src.infrastructure.translation.fake_engine import FakeTranslationEngine
from src.infrastructure.translation.ollama_engine import OllamaTranslationEngine


def test_ollama_config_valid():
    config = OllamaConfig(host="http://localhost:11434/", model="test", timeout_seconds=10)
    assert config.host == "http://localhost:11434"  # Check normalization
    assert config.model == "test"
    assert config.timeout_seconds == 10


def test_ollama_config_invalid_host():
    with pytest.raises(ValueError, match="Host cannot be empty"):
        OllamaConfig(host="   ")

    with pytest.raises(ValueError, match="Host cannot be empty"):
        OllamaConfig(host="")


def test_ollama_config_invalid_model():
    with pytest.raises(ValueError, match="Model cannot be empty"):
        OllamaConfig(model="   ")

    with pytest.raises(ValueError, match="Model cannot be empty"):
        OllamaConfig(model="")


def test_ollama_config_invalid_timeout():
    with pytest.raises(ValueError, match="Timeout must be > 0"):
        OllamaConfig(timeout_seconds=0)

    with pytest.raises(ValueError, match="Timeout must be > 0"):
        OllamaConfig(timeout_seconds=-5)


def test_composition_creates_fake_engine():
    env = {"TRANSLATOR_ENGINE": "fake"}
    engine = create_translation_engine(env)
    assert isinstance(engine, FakeTranslationEngine)


def test_composition_creates_ollama_engine():
    env = {"TRANSLATOR_ENGINE": "ollama"}
    engine = create_translation_engine(env)
    assert isinstance(engine, OllamaTranslationEngine)
    assert isinstance(engine.config, OllamaConfig)
    assert engine.config.host == "http://localhost:11434"


def test_composition_creates_ollama_engine_with_custom_config():
    env = {
        "TRANSLATOR_ENGINE": "ollama",
        "OLLAMA_MODEL": "custom:1b",
        "OLLAMA_TIMEOUT_SECONDS": "100",
    }
    engine = create_translation_engine(env)
    assert isinstance(engine, OllamaTranslationEngine)
    assert engine.config.model == "custom:1b"
    assert engine.config.timeout_seconds == 100.0


def test_composition_invalid_engine():
    env = {"TRANSLATOR_ENGINE": "unknown"}
    with pytest.raises(TranslationConfigurationError, match="Invalid translation engine type"):
        create_translation_engine(env)


def test_composition_fake_independent_of_ollama_config():
    # Fake should start even if OLLAMA_TIMEOUT_SECONDS is totally invalid
    env = {"TRANSLATOR_ENGINE": "fake", "OLLAMA_TIMEOUT_SECONDS": "INVALID_NUMBER"}
    engine = create_translation_engine(env)
    assert isinstance(engine, FakeTranslationEngine)


def test_composition_invalid_timeout_with_ollama():
    env = {"TRANSLATOR_ENGINE": "ollama", "OLLAMA_TIMEOUT_SECONDS": "INVALID_NUMBER"}
    with pytest.raises(TranslationConfigurationError, match="Invalid OLLAMA_TIMEOUT_SECONDS"):
        create_translation_engine(env)


def test_composition_engine_normalization():
    env = {"TRANSLATOR_ENGINE": "  OLLAMA  "}
    engine = create_translation_engine(env)
    assert isinstance(engine, OllamaTranslationEngine)
