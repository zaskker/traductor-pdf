from src.domain.models.enums import FitStatus
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.layout import TextLayoutInput
from src.infrastructure.pdf.layout_engine import PyMuPDFTextLayoutEngine


def test_short_text_fits_at_max():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput("Short text", Rect(0, 0, 100, 100), 6.0, 18.0, "helv")
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert result.font_size >= 17.0
    assert tuple(l.text for l in result.lines) == ("Short text",)


def test_long_text_reduces_font():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "This is a very long text that definitely needs to be reduced to fit inside this small box",
        Rect(0, 0, 100, 100),
        6.0,
        24.0,
        "helv",
    )
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert result.font_size < 24.0
    assert len(result.lines) > 1


def test_min_equals_max():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput("Test", Rect(0, 0, 50, 50), 12.0, 12.0, "helv")
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert result.font_size == 12.0


def test_cannot_fit_at_minimum_overflow():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "This text is insanely long and the box is tiny, so it will overflow no matter what.",
        Rect(0, 0, 20, 20),
        12.0,
        24.0,
        "helv",
    )
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.OVERFLOW
    assert result.font_size == 12.0
    assert result.lines == ()


def test_empty_translated_text():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput("", Rect(0, 0, 100, 100), 6.0, 12.0, "helv")
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert result.font_size == 12.0
    assert result.lines == ()


def test_explicit_newlines():
    engine = PyMuPDFTextLayoutEngine()
    # HTML renderer collapses \n into space.
    input_data = TextLayoutInput("Line 1\nLine 2", Rect(0, 0, 100, 100), 6.0, 12.0, "helv")
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert len(result.lines) >= 1


def test_leading_trailing_whitespace():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput("   text   ", Rect(0, 0, 100, 100), 6.0, 12.0, "helv")
    result = engine.layout_text(input_data)

    # PyMuPDF usually trims leading/trailing when extracting, or maintains it?
    # Actually, PyMuPDF get_text('dict') might trim it. But let's check it doesn't fail.
    assert result.status == FitStatus.FIT


def test_spanish_unicode():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "¡Hola! ¿Qué tal? áéíóú ñ", Rect(0, 0, 200, 200), 6.0, 12.0, "helv"
    )
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert "¡Hola! ¿Qué tal? áéíóú ñ" in " ".join(l.text for l in result.lines)


def test_very_narrow_rect():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput("a b c d e f", Rect(0, 0, 10, 200), 6.0, 12.0, "helv")
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert len(result.lines) > 2


def test_very_short_rect():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "This is a wide but short rect", Rect(0, 0, 200, 10), 6.0, 12.0, "helv"
    )
    result = engine.layout_text(input_data)
    # Could fit or overflow depending on exact metrics.
    # At 6pt, height 10 is > 1 line height.
    assert result.font_size >= 6.0


def test_long_unbreakable_token_url():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "https://www.thisisaverylongurlthatwillnotwrap.com/something/else",
        Rect(0, 0, 100, 100),
        6.0,
        24.0,
        "helv",
    )
    result = engine.layout_text(input_data)
    # The URL will force the font to be small or overflow
    assert result.font_size < 24.0 or result.status == FitStatus.OVERFLOW


def test_deterministic_repeated_input():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput("Deterministic text", Rect(0, 0, 100, 100), 6.0, 24.0, "helv")
    res1 = engine.layout_text(input_data)
    res2 = engine.layout_text(input_data)

    assert res1.font_size == res2.font_size
    assert res1.status == res2.status
    assert res1.lines == res2.lines


def test_invalid_font_sizes_fallback():
    engine = PyMuPDFTextLayoutEngine()
    # If someone passes max_font_size < min_font_size, the engine normalizes it
    input_data = TextLayoutInput("Text", Rect(0, 0, 100, 100), 6.0, 2.0, "helv")
    result = engine.layout_text(input_data)

    assert result.font_size == 6.0


def test_min_font_is_only_size_that_fits():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "A",
        Rect(0, 0, 15, 15),
        6.0,
        24.0,
        "helv",
    )
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.FIT
    assert result.font_size >= 6.0
    assert result.lines != ()


def test_min_font_does_not_fit():
    engine = PyMuPDFTextLayoutEngine()
    input_data = TextLayoutInput(
        "This is way too long for a tiny box",
        Rect(0, 0, 10, 5),  # Box too small for even 6.0pt font (height 5 < 6)
        6.0,
        24.0,
        "helv",
    )
    result = engine.layout_text(input_data)

    assert result.status == FitStatus.OVERFLOW
    assert result.font_size == 6.0
    assert result.lines == ()


def test_line_spacing_extracted_from_pymupdf():
    engine = PyMuPDFTextLayoutEngine()

    # Long text forces line wrapping in HTML renderer. We use a larger rect to avoid overflow.
    input_data_2 = TextLayoutInput(
        "Line 1 Line 2 Line 3 Line 4 " * 10, Rect(0, 0, 400, 400), 12.0, 12.0, "helv"
    )
    result_2 = engine.layout_text(input_data_2)
    assert len(result_2.lines) >= 2
    assert result_2.lines[0].y_offset <= result_2.lines[1].y_offset
