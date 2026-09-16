import pytest

from src.domain.value_objects.extraction import FragmentGranularity, SourceFragment
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.text_extractor import PyMuPDFTextExtractor


@pytest.fixture
def extractor():
    class DummyAdapter:
        pass

    return PyMuPDFTextExtractor(DummyAdapter())


def test_span_inclusion_rule():
    # User selection
    sel = Rect(0, 0, 100, 100)

    # Rule: has_center OR overlap_ratio >= 0.50

    # Case 1: center inside, overlap < 50% -> ACCEPTED because center is inside
    span_rect1 = Rect(-50, -50, 150, 150)
    intersect1 = span_rect1.intersect(sel)
    overlap1 = intersect1.area / span_rect1.area
    c1 = span_rect1.center
    has_center1 = sel.x0 <= c1.x <= sel.x1 and sel.y0 <= c1.y <= sel.y1
    assert has_center1 is True
    assert overlap1 == 0.25
    assert has_center1 or overlap1 >= 0.50

    # Case 2: overlap >= 50% -> ACCEPTED
    span_rect2 = Rect(50, 20, 60, 120)
    intersect2 = span_rect2.intersect(sel)
    overlap2 = intersect2.area / span_rect2.area
    c2 = span_rect2.center
    has_center2 = sel.x0 <= c2.x <= sel.x1 and sel.y0 <= c2.y <= sel.y1
    assert overlap2 == 0.80
    assert has_center2 or overlap2 >= 0.50

    # Case 3: center outside AND overlap < 50% -> REJECTED
    span_rect3 = Rect(50, 51, 60, 151)
    intersect3 = span_rect3.intersect(sel)
    overlap3 = intersect3.area / span_rect3.area
    c3 = span_rect3.center
    has_center3 = sel.x0 <= c3.x <= sel.x1 and sel.y0 <= c3.y <= sel.y1
    assert has_center3 is False
    assert overlap3 == 0.49
    assert not (has_center3 or overlap3 >= 0.50)


def test_space_gap_threshold(extractor):
    # Font size 12
    # Threshold = 0.15 * 12 = 1.8 pt
    # Test gaps: 1.2 (0.10), 1.68 (0.14), 1.8 (0.15), 1.92 (0.16), 2.4 (0.20)
    def check_space(gap):
        f1 = SourceFragment(
            text="A",
            bbox=Rect(0, 0, 10, 12),
            granularity=FragmentGranularity.WORD,
            block_index=0,
            line_index=0,
            span_index=0,
            raw_font_name="",
            font_size=12.0,
            font_color="",
            font_flags_raw=0,
            is_bold=False,
            is_italic=False,
            is_serif=False,
            is_monospace=False,
        )
        f2 = SourceFragment(
            text="B",
            bbox=Rect(10 + gap, 0, 20 + gap, 12),
            granularity=FragmentGranularity.WORD,
            block_index=0,
            line_index=0,
            span_index=0,
            raw_font_name="",
            font_size=12.0,
            font_color="",
            font_flags_raw=0,
            is_bold=False,
            is_italic=False,
            is_serif=False,
            is_monospace=False,
        )
        return extractor._reconstruct_text([f1, f2])

    assert check_space(1.2) == "AB"
    assert check_space(1.68) == "AB"
    assert check_space(1.79) == "AB"
    assert check_space(1.92) == "A B"
    assert check_space(2.4) == "A B"
