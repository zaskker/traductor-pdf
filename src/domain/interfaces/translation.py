from dataclasses import dataclass
from typing import Protocol

from enum import Enum

class TranslationError(Exception):
    """Base exception for translation errors."""


class TranslationEngineError(TranslationError):
    """Raised when the translation engine fails."""


class TranslationEngineUnavailableError(TranslationEngineError):
    """Raised when the translation engine is unreachable or offline."""


class TranslationModelNotFoundError(TranslationEngineError):
    """Raised when the requested model is not found on the engine."""


class TranslationTimeoutError(TranslationEngineError):
    """Raised when the translation engine times out."""


class TokenRestorationError(TranslationError):
    """Raised when a placeholder cannot be correctly restored in the translated text."""


class InvalidTranslationResultError(TranslationError):
    """Raised when the returned translation result violates invariants."""


class StructuralMarkerMismatchError(InvalidTranslationResultError):
    """Raised when the returned translation has missing, extra, or duplicated structural markers."""
    def __init__(self, message: str, expected_markers: list[str], found_markers: list[str]):
        super().__init__(message)
        self.expected_markers = expected_markers
        self.found_markers = found_markers


class GlossaryMismatchError(TranslationError):
    """Raised when the returned translation does not comply with the project glossary."""


class StaleTranslationRevisionError(Exception):
    """
    Raised when a review or approval action targets an expected translation_revision
    that no longer matches the current revision of the region.
    The UI should refresh and display the current state to the user.
    """


class TranslationNotReviewedError(Exception):
    """
    Raised when attempting to approve a translation that has not been marked as reviewed.
    Flow must be: REVIEWED -> APPROVED. Going UNREVIEWED -> APPROVED is not allowed.
    """


@dataclass(frozen=True)
class TranslationResult:
    translated_text: str
    engine_name: str
    model_name: str

    def __post_init__(self):
        if not self.engine_name.strip():
            raise InvalidTranslationResultError("engine_name cannot be empty")


class EngineStatus(Enum):
    UNKNOWN = "unknown"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    MODEL_MISSING = "model_missing"


@dataclass(frozen=True)
class TranslationEngineInfo:
    provider: str
    model: str
    status: EngineStatus


class ITranslationEngine(Protocol):
    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> TranslationResult: ...

    def get_info(self) -> TranslationEngineInfo: ...

    def check_availability(self) -> TranslationEngineInfo: ...
