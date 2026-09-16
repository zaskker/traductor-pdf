from src.application.services.prompt_builder import TranslationPromptBuilder


def test_prompt_builder_includes_languages():
    builder = TranslationPromptBuilder()
    sys_prompt = builder.build_system_prompt("English", "Spanish")

    assert "English" in sys_prompt
    assert "Spanish" in sys_prompt


def test_prompt_builder_rules():
    builder = TranslationPromptBuilder()
    sys_prompt = builder.build_system_prompt("en", "es")

    assert "Output ONLY the translation" in sys_prompt
    assert "DATA TO TRANSLATE enclosed in <TRANSLATION_SOURCE> tags" in sys_prompt


def test_prompt_builder_user_prompt():
    builder = TranslationPromptBuilder()
    text = "Hello world [[TP_0001]]"
    user_prompt = builder.build_user_prompt(text)

    assert "<TRANSLATION_SOURCE>\nHello world [[TP_0001]]\n</TRANSLATION_SOURCE>" in user_prompt


def test_prompt_builder_delimiter_collision():
    builder = TranslationPromptBuilder()
    text = "Some text with <TRANSLATION_SOURCE> and </TRANSLATION_SOURCE> inside."
    user_prompt = builder.build_user_prompt(text)

    assert "<\\TRANSLATION_SOURCE>" in user_prompt
    assert "<\\/TRANSLATION_SOURCE>" in user_prompt

    # Assert outer delimiters are intact
    assert user_prompt.startswith("<TRANSLATION_SOURCE>\n")
    assert user_prompt.endswith("\n</TRANSLATION_SOURCE>")


def test_prompt_builder_structured_mode():
    builder = TranslationPromptBuilder()
    sys_prompt = builder.build_system_prompt("en", "es", structured_mode=True)
    assert "[[BLOCK_0000]]" in sys_prompt
    assert "Preserve every BLOCK marker EXACTLY ONCE" in sys_prompt

