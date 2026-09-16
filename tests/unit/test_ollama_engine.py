import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from src.domain.interfaces.translation import (
    InvalidTranslationResultError,
    TranslationEngineError,
    TranslationTimeoutError,
)
from src.infrastructure.translation.config import OllamaConfig
from src.infrastructure.translation.ollama_engine import OllamaTranslationEngine


@pytest.fixture
def config():
    return OllamaConfig(host="http://localhost:11434", model="llama3.2:3b", timeout_seconds=10)


@pytest.fixture
def engine(config):
    return OllamaTranslationEngine(config)


def create_mock_response(body: str, status: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = body.encode("utf-8")
    mock_resp.status = status
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_ollama_engine_success(engine):
    valid_json = '{"response": "Hola Mundo", "done": true}'
    mock_resp = create_mock_response(valid_json)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = engine.translate("System rules", "Hello World")

    assert res.translated_text == "Hola Mundo"
    assert res.engine_name == "ollama"
    assert res.model_name == "llama3.2:3b"

    # Verify request
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "http://localhost:11434/api/generate"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["model"] == "llama3.2:3b"
    assert payload["system"] == "System rules"
    assert payload["prompt"] == "Hello World"
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0.0


def test_ollama_engine_connection_refused(engine):
    with (
        patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError(ConnectionRefusedError())
        ),
        pytest.raises(TranslationEngineError, match="Ollama is unreachable"),
    ):
        engine.translate("System rules", "Hello")


def test_ollama_engine_timeout(engine):
    with (
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError(TimeoutError())),
        pytest.raises(TranslationTimeoutError, match="timed out"),
    ):
        engine.translate("System rules", "Hello")

    with (
        patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")),
        pytest.raises(TranslationTimeoutError, match="timed out"),
    ):
        engine.translate("System rules", "Hello")


def test_ollama_engine_404_model_missing(engine):
    error_body = '{"error": "model \'llama3.2:3b\' not found"}'
    mock_err = urllib.error.HTTPError(
        url="http://localhost:11434/api/generate",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=create_mock_response(error_body),
    )
    with (
        patch("urllib.request.urlopen", side_effect=mock_err),
        pytest.raises(TranslationEngineError, match="not available in Ollama"),
    ):
        engine.translate("System rules", "Hello")


def test_ollama_engine_404_generic(engine):
    error_body = '{"error": "some other 404 error"}'
    mock_err = urllib.error.HTTPError(
        url="http://localhost:11434/api/generate",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=create_mock_response(error_body),
    )
    with (
        patch("urllib.request.urlopen", side_effect=mock_err),
        pytest.raises(TranslationEngineError, match="Endpoint not found"),
    ):
        engine.translate("System rules", "Hello")


def test_ollama_engine_500_error(engine):
    mock_err = urllib.error.HTTPError(
        url="http://localhost:11434/api/generate",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=None,
    )
    with (
        patch("urllib.request.urlopen", side_effect=mock_err),
        pytest.raises(TranslationEngineError, match="HTTP Error 500"),
    ):
        engine.translate("System rules", "Hello")


def test_ollama_engine_invalid_json(engine):
    mock_resp = create_mock_response("{invalid json")
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(TranslationEngineError, match="Invalid JSON response"),
    ):
        engine.translate("Sys", "Hello")


def test_ollama_engine_json_not_object(engine):
    mock_resp = create_mock_response('["array", "not", "object"]')
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(TranslationEngineError, match="expected object"),
    ):
        engine.translate("Sys", "Hello")


def test_ollama_engine_missing_response_field(engine):
    mock_resp = create_mock_response('{"done": true}')
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(InvalidTranslationResultError, match="Missing 'response' field"),
    ):
        engine.translate("Sys", "Hello")


@pytest.mark.parametrize(
    "invalid_response",
    [
        None,
        123,
        True,
    ],
)
def test_ollama_engine_response_invalid_type(engine, invalid_response):
    payload = {"done": True, "response": invalid_response}
    mock_resp = create_mock_response(json.dumps(payload))
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(InvalidTranslationResultError, match="expected string"),
    ):
        engine.translate("Sys", "Hello")


@pytest.mark.parametrize(
    "empty_response",
    [
        "",
        "   ",
        "\n",
    ],
)
def test_ollama_engine_response_empty(engine, empty_response):
    payload = {"done": True, "response": empty_response}
    mock_resp = create_mock_response(json.dumps(payload))
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(InvalidTranslationResultError, match="Missing or empty response field"),
    ):
        engine.translate("Sys", "Hello")
