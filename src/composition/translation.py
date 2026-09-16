import os

from src.domain.interfaces.translation import ITranslationEngine
from src.infrastructure.translation.config import OllamaConfig
from src.infrastructure.translation.fake_engine import FakeTranslationEngine
from src.infrastructure.translation.ollama_engine import OllamaTranslationEngine


class TranslationConfigurationError(Exception):
    """Raised when there is an invalid configuration for the translation engine."""


def create_translation_engine(env: dict[str, str] | None = None) -> ITranslationEngine:
    """
    Creates the appropriate ITranslationEngine based on environment configuration.
    """
    if env is None:
        env = os.environ

    engine_type = env.get("TRANSLATOR_ENGINE", "ollama").strip().lower()

    if engine_type == "fake":
        return FakeTranslationEngine()

    if engine_type == "ollama":
        host = env.get("OLLAMA_HOST", "http://localhost:11434").strip()
        model = env.get("OLLAMA_MODEL", "llama3.2:3b").strip()
        timeout_str = env.get("OLLAMA_TIMEOUT_SECONDS", "300").strip()

        try:
            timeout = float(timeout_str)
        except ValueError as e:
            raise TranslationConfigurationError(
                f"Invalid OLLAMA_TIMEOUT_SECONDS: '{timeout_str}'. Must be a number."
            ) from e

        try:
            config = OllamaConfig(host=host, model=model, timeout_seconds=timeout)
        except ValueError as e:
            raise TranslationConfigurationError(f"Invalid Ollama configuration: {e!s}") from e

        return OllamaTranslationEngine(config)

    raise TranslationConfigurationError(
        f"Invalid translation engine type: '{engine_type}'. Supported values are 'fake', 'ollama'."
    )
