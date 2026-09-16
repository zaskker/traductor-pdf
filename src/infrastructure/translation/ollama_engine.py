import json
import socket
import urllib.error
import urllib.request
from typing import Any

from src.application.logger import logger
from src.domain.interfaces.translation import (
    InvalidTranslationResultError,
    ITranslationEngine,
    TranslationEngineError,
    TranslationEngineUnavailableError,
    TranslationModelNotFoundError,
    TranslationResult,
    TranslationTimeoutError,
    TranslationEngineInfo,
    EngineStatus,
)
from src.infrastructure.translation.config import OllamaConfig


class OllamaTranslationEngine(ITranslationEngine):
    def __init__(self, config: OllamaConfig):
        self.config = config
        self._endpoint = f"{self.config.host}/api/generate"
        self._tags_endpoint = f"{self.config.host}/api/tags"
        self._last_status = EngineStatus.UNKNOWN

    def get_info(self) -> TranslationEngineInfo:
        return TranslationEngineInfo(
            provider="ollama",
            model=self.config.model,
            status=self._last_status,
        )

    def check_availability(self) -> TranslationEngineInfo:
        """Checks availability by hitting /api/tags synchronously."""
        req = urllib.request.Request(self._tags_endpoint, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5.0) as response:
                data = json.loads(response.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                if self.config.model in models:
                    self._last_status = EngineStatus.READY
                else:
                    # sometimes ollama returns model names with :latest, check prefix if exact fails
                    if not any(m.startswith(self.config.model) for m in models):
                        self._last_status = EngineStatus.MODEL_MISSING
                    else:
                        self._last_status = EngineStatus.READY
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError):
            self._last_status = EngineStatus.UNAVAILABLE
        except Exception:
            self._last_status = EngineStatus.UNAVAILABLE
            
        return self.get_info()

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> TranslationResult:
        payload = {
            "model": self.config.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint, data=data, headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                response_data = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                try:
                    error_body = e.read().decode("utf-8")
                    error_json = json.loads(error_body)
                    if "not found" in error_json.get("error", "").lower():
                        raise TranslationModelNotFoundError(
                            f"Model '{self.config.model}' is not available in Ollama."
                        ) from e
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                raise TranslationEngineUnavailableError(
                    f"HTTP Error 404: Endpoint not found at {self._endpoint}"
                ) from e
            raise TranslationEngineError(f"HTTP Error {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise TranslationTimeoutError("Translation request timed out.") from e
            if isinstance(e.reason, ConnectionRefusedError):
                raise TranslationEngineUnavailableError(
                    f"Ollama is unreachable (connection refused). Please ensure it is running at {self.config.host}."
                ) from e
            raise TranslationEngineUnavailableError(
                f"Ollama is unreachable. Please ensure it is running at {self.config.host}."
            ) from e
        except TimeoutError as e:
            raise TranslationTimeoutError("Translation request timed out.") from e
        except ConnectionError as e:
            raise TranslationEngineUnavailableError(f"Connection error: {e!s}") from e
        except Exception as e:
            # Catch-all for other low-level socket issues to prevent raw exceptions leaking
            raise TranslationEngineError(f"Unexpected connection error: {e!s}") from e

        # Validate Response
        try:
            result_json: dict[str, Any] = json.loads(response_data)
        except json.JSONDecodeError as e:
            raise TranslationEngineError("Invalid JSON response from engine.") from e

        if not isinstance(result_json, dict):
            raise TranslationEngineError("Invalid JSON response from engine: expected object.")

        if "response" not in result_json:
            raise InvalidTranslationResultError("Missing 'response' field in engine output.")

        translation_text = result_json["response"]

        if translation_text is None or isinstance(translation_text, (int, float, bool)):
            raise InvalidTranslationResultError(
                "Invalid 'response' field in engine output: expected string."
            )

        if not isinstance(translation_text, str) or not translation_text.strip():
            raise InvalidTranslationResultError("Missing or empty response field in engine output.")

        # Log purely technical metadata, no prompts/text
        duration = (
            result_json.get("total_duration", 0) / 1e9
        )  # Convert from nanoseconds if available
        logger.info(
            f"Ollama translation successful. Model={self.config.model}, duration={duration:.2f}s"
        )

        return TranslationResult(
            translated_text=translation_text,
            engine_name="ollama",
            model_name=self.config.model,
        )
