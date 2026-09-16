import os

import pytest

from src.composition.translation import create_translation_engine
from src.infrastructure.translation.config import OllamaConfig


@pytest.mark.ollama
@pytest.mark.skipif(
    os.environ.get("RUN_OLLAMA_TESTS") != "1", reason="Requires real Ollama instance running"
)
def test_real_ollama_translation():
    """
    Smoke test to verify Ollama Integration.
    Requires RUN_OLLAMA_TESTS=1 environment variable and Ollama running locally with the configured model.
    """
    config = OllamaConfig(
        host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        model=os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
        timeout_seconds=300,
    )
    engine = create_translation_engine("ollama", config)

    system_prompt = "You are a professional technical translator. Translate English to Spanish. Output ONLY the translation."
    user_prompt = "<TRANSLATION_SOURCE>\nHello World\n</TRANSLATION_SOURCE>"

    result = engine.translate(system_prompt, user_prompt)

    assert result.translated_text
    assert result.engine_name == "ollama"
    assert result.model_name == config.model
    # Just checking it didn't fail and gave something back.
    # It should roughly contain "Hola" or "Mundo".
    assert (
        "Hola" in result.translated_text
        or "Mundo" in result.translated_text
        or "mundo" in result.translated_text.lower()
    )
