import pytest

from src.application.services.token_protector import TokenProtector
from src.domain.interfaces.translation import TokenRestorationError


@pytest.fixture
def protector():
    return TokenProtector()


def test_protect_no_tokens(protector):
    text = "This is a normal text."
    result = protector.protect(text)
    assert result.text == text
    assert len(result.placeholders) == 0


def test_protect_empty_text(protector):
    result = protector.protect("")
    assert result.text == ""
    assert len(result.placeholders) == 0


def test_protect_url(protector):
    text = "Visit https://example.com/docs for info."
    result = protector.protect(text)
    assert result.text == "Visit [[TP_0001]] for info."
    assert result.placeholders["[[TP_0001]]"] == "https://example.com/docs"


def test_protect_localhost_url(protector):
    text = "See http://localhost:11434/api/generate"
    result = protector.protect(text)
    assert result.text == "See [[TP_0001]]"
    assert result.placeholders["[[TP_0001]]"] == "http://localhost:11434/api/generate"


def test_protect_windows_path(protector):
    text = "File is in C:\\Users\\name\\file.txt."
    result = protector.protect(text)
    assert result.text == "File is in [[TP_0001]]."
    assert result.placeholders["[[TP_0001]]"] == "C:\\Users\\name\\file.txt"


def test_protect_posix_path(protector):
    text = "Path /usr/local/bin/python is valid."
    result = protector.protect(text)
    assert result.text == "Path [[TP_0001]] is valid."
    assert result.placeholders["[[TP_0001]]"] == "/usr/local/bin/python"


def test_protect_cli_flags(protector):
    text = "Run with --verbose, --output=file.txt or -o flag."
    result = protector.protect(text)
    assert result.text == "Run with [[TP_0001]], [[TP_0002]] or [[TP_0003]] flag."
    assert result.placeholders["[[TP_0001]]"] == "--verbose"
    assert result.placeholders["[[TP_0002]]"] == "--output=file.txt"
    assert result.placeholders["[[TP_0003]]"] == "-o"


def test_protect_inline_command(protector):
    text = "Type `pip install pymupdf` to install."
    result = protector.protect(text)
    assert result.text == "Type [[TP_0001]] to install."
    assert result.placeholders["[[TP_0001]]"] == "`pip install pymupdf`"


def test_protect_variables(protector):
    text = "User $foo, ${bar}, and %BAZ%."
    protected = protector.protect(text)

    assert "[[TP_0001]]" in protected.text
    assert "[[TP_0002]]" in protected.text
    assert "[[TP_0003]]" in protected.text
    assert list(protected.placeholders.values()) == ["$foo", "${bar}", "%BAZ%"]


def test_protect_html_tags(protector):
    text = "Click <Button> to save. <br/> </config>"
    protected = protector.protect(text)

    assert "[[TP_0001]]" in protected.text
    assert "[[TP_0002]]" in protected.text
    assert "[[TP_0003]]" in protected.text
    assert list(protected.placeholders.values()) == ["<Button>", "<br/>", "</config>"]


def test_protect_emails(protector):
    text = "Contact support@example.com or user.name+test@sub.domain.co.uk today."
    protected = protector.protect(text)

    assert "[[TP_0001]]" in protected.text
    assert "[[TP_0002]]" in protected.text
    assert list(protected.placeholders.values()) == [
        "support@example.com",
        "user.name+test@sub.domain.co.uk",
    ]


def test_protect_file_extensions(protector):
    text = "Edit script.js, data.json, and style.css in the folder."
    protected = protector.protect(text)

    assert "[[TP_0001]]" in protected.text
    assert "[[TP_0002]]" in protected.text
    assert "[[TP_0003]]" in protected.text
    assert list(protected.placeholders.values()) == ["script.js", "data.json", "style.css"]


def test_protect_numbers_are_ignored(protector):
    text = "It costs 1,000.50 or $50 to buy 2."
    protected = protector.protect(text)
    # $50 is matched as a variable, but 1,000.50 is not matched
    assert "1,000.50" in protected.text
    assert "2." in protected.text


def test_protect_multiple_and_overlapping(protector):
    # Path inside code block should be handled by code block first
    text = "Use `cat /etc/passwd` and visit http://localhost"
    result = protector.protect(text)
    assert result.text == "Use [[TP_0001]] and visit [[TP_0002]]"
    assert result.placeholders["[[TP_0001]]"] == "`cat /etc/passwd`"
    assert result.placeholders["[[TP_0002]]"] == "http://localhost"


def test_protect_source_already_contains_tp_like_placeholder(protector):
    text = "This text has [[TP_0005]] inside."
    result = protector.protect(text)
    assert result.text == "This text has [[TP_0001]] inside."
    assert result.placeholders["[[TP_0001]]"] == "[[TP_0005]]"


def test_restore_success(protector):
    text = "URL is https://google.com"
    protected = protector.protect(text)
    # Simulate LLM translating the rest
    translated = f"La URL es {next(iter(protected.placeholders.keys()))}"
    restored = protector.restore(translated, protected)
    assert restored == "La URL es https://google.com"


def test_restore_missing_placeholder(protector):
    text = "URL https://google.com and https://bing.com"
    protected = protector.protect(text)
    translated = f"URL {next(iter(protected.placeholders.keys()))}"
    with pytest.raises(TokenRestorationError, match="Missing placeholder"):
        protector.restore(translated, protected)


def test_restore_duplicate_placeholder(protector):
    text = "URL https://google.com"
    protected = protector.protect(text)
    tp = next(iter(protected.placeholders.keys()))
    translated = f"URL {tp} and another {tp}"
    with pytest.raises(TokenRestorationError, match="Duplicate placeholder"):
        protector.restore(translated, protected)


def test_restore_unknown_placeholder(protector):
    text = "URL https://google.com"
    protected = protector.protect(text)
    tp = next(iter(protected.placeholders.keys()))
    translated = f"URL {tp} and [[TP_0099]]"
    with pytest.raises(TokenRestorationError, match="Unknown or modified placeholder"):
        protector.restore(translated, protected)


def test_restore_modified_placeholder(protector):
    text = "URL https://google.com"
    protected = protector.protect(text)
    translated = "URL [[TP-0001]]"
    # modified placeholder means it's missing the real one
    with pytest.raises(TokenRestorationError, match="Missing placeholder"):
        protector.restore(translated, protected)

    translated2 = "URL [[TP_001]]"
    with pytest.raises(TokenRestorationError, match="Missing placeholder"):
        protector.restore(translated2, protected)


def test_restore_collision_single_pass(protector):
    """
    Simulates the exact collision bug reported:
    If a protected text resolves to something that looks like another token,
    a sequential .replace() would wrongly replace it again.
    """
    text = "Existing [[TP_0002]] then https://example.com"
    protected = protector.protect(text)

    assert protected.text == "Existing [[TP_0001]] then [[TP_0002]]"
    assert protected.placeholders["[[TP_0001]]"] == "[[TP_0002]]"
    assert protected.placeholders["[[TP_0002]]"] == "https://example.com"

    restored = protector.restore(protected.text, protected)
    assert restored == text


@pytest.mark.parametrize(
    "source",
    [
        "Existing [[TP_0002]] then https://example.com",
        "[[TP_0001]] + https://example.com",
        "https://example.com + [[TP_0001]]",
        "[[TP_0002]] + https://example.com",
        "https://example.com + [[TP_0002]]",
        "Tokens: [[TP_0003]], [[TP_0005]], C:\\path, --flag, `inline code` and ${VAR}",
        "A [[TP_0001]] followed by C:\\foo\\bar.txt and https://test.com",
        "Nested-like: `https://test.com` with C:\\test",
    ],
)
def test_restore_roundtrip_collisions(protector, source):
    protected = protector.protect(source)
    restored = protector.restore(protected.text, protected)
    assert restored == source


def test_token_overlap_priority(protector):
    """
    Test that higher priority rules (like XML/code/email) win over lower priority rules (paths).
    """
    text = "Send to <email>user@domain.com</email> in `config.json`"
    protected = protector.protect(text)
    assert list(protected.placeholders.values()) == [
        "<email>",
        "user@domain.com",
        "</email>",
        "`config.json`",
    ]


def test_protect_ignores_block_markers(protector):
    text = "[[BLOCK_0000]]\nText with https://example.com"
    protected = protector.protect(text)
    
    # Should only protect the URL, leaving BLOCK marker intact
    assert "[[BLOCK_0000]]" in protected.text
    assert "[[TP_0001]]" in protected.text
    assert list(protected.placeholders.values()) == ["https://example.com"]

