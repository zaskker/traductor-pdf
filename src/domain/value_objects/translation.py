from dataclasses import dataclass, field


@dataclass
class TranslationRequest:
    text: str
    source_language: str = "en"
    target_language: str = "es"
    protected_tokens: dict[str, str] = field(default_factory=dict)
    context: dict[str, str] = field(default_factory=dict)


@dataclass
class TranslationResult:
    translated_text: str
    engine: str
    model: str
    warnings: list[str] = field(default_factory=list)
