import pytest

from src.domain.value_objects.extraction import FragmentGranularity, SourceFragment
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.text_extractor import PyMuPDFTextExtractor


@pytest.fixture
def extractor():
    class DummyAdapter:
        pass

    return PyMuPDFTextExtractor(DummyAdapter())


def _make_frag(
    text: str,
    x0: float,
    x1: float,
    b_idx: int = 0,
    l_idx: int = 0,
    s_idx: int = 0,
    gran=FragmentGranularity.WORD,
) -> SourceFragment:
    return SourceFragment(
        text=text,
        bbox=Rect(x0, 10, x1, 22),  # 12pt font size (22-10)
        granularity=gran,
        block_index=b_idx,
        line_index=l_idx,
        span_index=s_idx,
        raw_font_name="helv",
        font_size=12.0,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False,
    )


def test_span_to_span(extractor):
    # SPAN containing "Threat " + SPAN containing "intelligence"
    # Gap is 0 since the space is included in the first span's bbox
    f1 = _make_frag("Threat ", 50.0, 80.0, s_idx=0, gran=FragmentGranularity.SPAN)
    f2 = _make_frag("intelligence", 80.0, 120.0, s_idx=1, gran=FragmentGranularity.SPAN)

    result = extractor._reconstruct_text([f1, f2])
    assert result == "Threat intelligence"


def test_word_to_word(extractor):
    # WORD "Threat" + WORD "intelligence"
    # PyMuPDF get_text("words") strips spaces, so we have a geometric gap.
    # Gap = 83.0 - 80.0 = 3.0 pt. 3.0 > 0.15 * 12 (1.8). So it adds space.
    f1 = _make_frag("Threat", 50.0, 80.0, s_idx=0, gran=FragmentGranularity.WORD)
    f2 = _make_frag("intelligence", 83.0, 120.0, s_idx=0, gran=FragmentGranularity.WORD)

    result = extractor._reconstruct_text([f1, f2])
    assert result == "Threat intelligence"


def test_word_to_word_no_space(extractor):
    # Two parts of a word artificially split (e.g. Threatintelligence)
    # Gap = 80.5 - 80.0 = 0.5 pt. 0.5 < 1.8. No space added.
    f1 = _make_frag("Threat", 50.0, 80.0, s_idx=0, gran=FragmentGranularity.WORD)
    f2 = _make_frag("intelligence", 80.5, 120.0, s_idx=0, gran=FragmentGranularity.WORD)

    result = extractor._reconstruct_text([f1, f2])
    assert result == "Threatintelligence"


def test_word_to_span(extractor):
    # WORD "Threat" + SPAN " intelligence"
    # Gap = 83.0 - 80.0 = 3.0 pt. It WOULD add a space, but line_str doesn't end with space yet.
    # So it adds space before " intelligence", resulting in double space?
    # No, wait. We add space AFTER f1.
    f1 = _make_frag("Threat", 50.0, 80.0, s_idx=0, gran=FragmentGranularity.WORD)
    f2 = _make_frag(" intelligence", 83.0, 120.0, s_idx=1, gran=FragmentGranularity.SPAN)

    # Gap is 3.0 -> space injected -> "Threat " + " intelligence" = "Threat  intelligence"
    # Wait, if f2 starts with space, we might get double space!
    # Let's fix this in _reconstruct_text. We shouldn't add a space if the next fragment STARTS with a space!
    result = extractor._reconstruct_text([f1, f2])
    assert (
        result == "Threat intelligence"
    )  # The test will fail right now! We need to adjust _reconstruct_text to handle this.


def test_span_to_word(extractor):
    # SPAN "Threat " + WORD "intelligence"
    # line_str ends with space, so no geometric space injected!
    f1 = _make_frag("Threat ", 50.0, 80.0, s_idx=0, gran=FragmentGranularity.SPAN)
    f2 = _make_frag("intelligence", 80.0, 120.0, s_idx=1, gran=FragmentGranularity.WORD)

    result = extractor._reconstruct_text([f1, f2])
    assert result == "Threat intelligence"


def test_multiple_lines_and_blocks(extractor):
    f1 = _make_frag("Line 1", 50.0, 80.0, b_idx=0, l_idx=0)
    f2 = _make_frag("Line 2", 50.0, 80.0, b_idx=0, l_idx=1)
    f3 = _make_frag("Block 2", 50.0, 80.0, b_idx=1, l_idx=0)

    result = extractor._reconstruct_text([f1, f2, f3])
    assert result == "Line 1\nLine 2\n\nBlock 2"
