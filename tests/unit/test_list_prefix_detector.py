"""Tests for list_prefix_detector.py."""

import pytest

from src.application.services.list_prefix_detector import detect_list_prefix, format_list_block


@pytest.mark.parametrize(
    "text,expected_prefix,expected_body",
    [
        ("7. You may now return", "7. ", "You may now return"),
        ("1. First item", "1. ", "First item"),
        ("1) First item", "1) ", "First item"),
        ("a. Sub-item", "a. ", "Sub-item"),
        ("a) Sub-item", "a) ", "Sub-item"),
        ("A. Major item", "A. ", "Major item"),
        ("(1) Parenthetical", "(1) ", "Parenthetical"),
        ("- Dash bullet", "- ", "Dash bullet"),
        ("• Bullet point", "• ", "Bullet point"),
        ("* Star bullet", "* ", "Star bullet"),
        ("– En-dash bullet", "– ", "En-dash bullet"),
    ],
)
def test_detect_list_prefix(text, expected_prefix, expected_body):
    result = detect_list_prefix(text)
    assert result is not None, f"Expected prefix detection for: {repr(text)}"
    assert result.prefix == expected_prefix
    assert result.body == expected_body


@pytest.mark.parametrize(
    "text",
    [
        "Figure 2.21 – IP while on proxy",
        "You may now return, remove your proxy.",
        "Normal sentence without prefix.",
        "",
        "   ",
        "https://www.example.com",
    ],
)
def test_no_list_prefix(text):
    result = detect_list_prefix(text)
    assert result is None, f"Unexpected prefix detection for: {repr(text)}"


def test_format_list_block_normalises_spacing():
    result = format_list_block("7.  ", "  Ahora puede volver")
    assert result == "7. Ahora puede volver"


def test_format_list_block_preserves_bullet():
    result = format_list_block("•  ", "Punto de viñeta")
    assert result == "• Punto de viñeta"
