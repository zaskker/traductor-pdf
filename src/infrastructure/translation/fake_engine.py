from src.domain.interfaces.translation import (
    EngineStatus,
    ITranslationEngine,
    TranslationEngineError,
    TranslationEngineInfo,
    TranslationResult,
    TranslationTimeoutError,
)


class FakeTranslationEngine(ITranslationEngine):
    """
    Fake engine for tests that returns deterministic translations.
    """
    def __init__(self, fail_percentage=0.0):
        self.fail_percentage = fail_percentage
        self.call_count = 0
        self.should_fail = False
        self.should_timeout = False
        self.configured_mapping = {}
        self.responses: list[str] = []

    def get_info(self) -> TranslationEngineInfo:
        return TranslationEngineInfo(
            provider="FakeProvider",
            model="fake-model",
            status=EngineStatus.READY,
        )

    def check_availability(self) -> TranslationEngineInfo:
        return self.get_info()

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> TranslationResult:
        self.call_count += 1

        if self.responses:
            next_response = self.responses.pop(0)
            return TranslationResult(
                translated_text=next_response,
                engine_name="FakeEngine",
                model_name="fake-v1",
            )

        if self.should_timeout:
            raise TranslationTimeoutError("Fake timeout occurred")

        if self.should_fail:
            raise TranslationEngineError("Fake engine failure")

        # Extract inner text to maintain compatibility with existing test configurations
        # that map "Hello" -> "Hola" instead of the full user_prompt.
        inner_text = user_prompt
        prefix = "<TRANSLATION_SOURCE>\n"
        suffix = "\n</TRANSLATION_SOURCE>"
        if user_prompt.startswith(prefix) and user_prompt.endswith(suffix):
            inner_text = user_prompt[len(prefix) : -len(suffix)]

        translated = self.configured_mapping.get(inner_text, f"[TRANSLATED] {inner_text}")
        if "[[BLOCK_" in inner_text and inner_text not in self.configured_mapping:
            translated = inner_text

        return TranslationResult(
            translated_text=translated,
            engine_name="FakeEngine",
            model_name="FakeModel",
        )
