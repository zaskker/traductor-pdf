"""
Tests for block_grouper.py using REAL SourceFragment domain objects.
No mocks, no SimpleNamespace.
"""

import pytest

from src.application.services.block_grouper import (
    group_source_fragments_into_blocks,
    group_source_fragments_into_lines,
)
from src.domain.models.enums import ExtractionMethod
from src.domain.value_objects.extraction import FragmentGranularity, SourceFragment
from src.domain.value_objects.geometry import Rect


def _frag(
    text: str,
    block_index: int,
    line_index: int,
    span_index: int,
    x0: float = 0.0,
    y0: float = 0.0,
    x1: float = 100.0,
    y1: float | None = None,
    font_size: float = 12.0,
) -> SourceFragment:
    if y1 is None:
        y1 = y0 + 12.0
    return SourceFragment(
        text=text,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        granularity=FragmentGranularity.SPAN,
        block_index=block_index,
        line_index=line_index,
        span_index=span_index,
        raw_font_name="Helvetica",
        font_size=font_size,
        font_color="#000000",
        font_flags_raw=0,
        is_bold=False,
        is_italic=False,
        is_serif=False,
        is_monospace=False,
    )


class TestGroupSourceFragmentsIntoLines:
    def test_empty_returns_empty(self):
        assert group_source_fragments_into_lines(()) == ()

    def test_single_fragment_single_line(self):
        frags = (_frag("Hello", block_index=0, line_index=0, span_index=0),)
        lines = group_source_fragments_into_lines(frags)
        assert len(lines) == 1
        assert lines[0].text == "Hello"
        assert lines[0].block_index == 0
        assert lines[0].line_index == 0

    def test_two_spans_on_same_line_concatenated(self):
        frags = (
            _frag("Figure ", block_index=0, line_index=0, span_index=0, x0=0, x1=50),
            _frag("2.21 – IP", block_index=0, line_index=0, span_index=1, x0=50, x1=120),
        )
        lines = group_source_fragments_into_lines(frags)
        assert len(lines) == 1
        assert "Figure " in lines[0].text
        assert "2.21" in lines[0].text

    def test_two_blocks_two_lines(self):
        """Caption block + list item block → 2 separate lines."""
        frags = (
            _frag(
                "Figure 2.21 – IP while on proxy",
                block_index=0,
                line_index=0,
                span_index=0,
                y0=50,
                y1=62,
            ),
            _frag(
                "7. You may now return...", block_index=1, line_index=0, span_index=0, y0=80, y1=92
            ),
        )
        lines = group_source_fragments_into_lines(frags)
        assert len(lines) == 2
        assert lines[0].block_index == 0
        assert lines[1].block_index == 1

    def test_sorting_by_block_then_line(self):
        """Lines are returned in block_index ASC, line_index ASC order."""
        frags = (
            _frag("line 1-0", block_index=1, line_index=0, span_index=0, y0=80),
            _frag("line 0-0", block_index=0, line_index=0, span_index=0, y0=50),
            _frag("line 0-1", block_index=0, line_index=1, span_index=0, y0=65),
        )
        lines = group_source_fragments_into_lines(frags)
        assert len(lines) == 3
        assert lines[0].block_index == 0 and lines[0].line_index == 0
        assert lines[1].block_index == 0 and lines[1].line_index == 1
        assert lines[2].block_index == 1

    def test_font_size_max_of_spans(self):
        """Font size of the line is the max font_size of its fragments."""
        frags = (
            _frag("A", block_index=0, line_index=0, span_index=0, font_size=10.0),
            _frag("B", block_index=0, line_index=0, span_index=1, font_size=14.0),
        )
        lines = group_source_fragments_into_lines(frags)
        assert lines[0].font_size == 14.0

    def test_bbox_union(self):
        """Line bbox is the union of all fragment bboxes."""
        frags = (
            _frag("A", block_index=0, line_index=0, span_index=0, x0=10, y0=50, x1=50, y1=62),
            _frag("B", block_index=0, line_index=0, span_index=1, x0=50, y0=50, x1=120, y1=62),
        )
        lines = group_source_fragments_into_lines(frags)
        bbox = lines[0].bbox
        assert bbox.x0 == 10.0
        assert bbox.x1 == 120.0
        assert bbox.y0 == 50.0
        assert bbox.y1 == 62.0


class TestGroupSourceFragmentsIntoBlocks:
    def test_empty_returns_empty(self):
        assert group_source_fragments_into_blocks(()) == ()

    def test_single_block_single_line(self):
        frags = (_frag("Hello world", block_index=0, line_index=0, span_index=0),)
        blocks = group_source_fragments_into_blocks(frags)
        assert len(blocks) == 1
        assert "Hello world" in blocks[0].text

    def test_multi_line_single_block_joins_with_space(self):
        """Multiple lines in same block are joined with space."""
        frags = (
            _frag("You may now return,", block_index=0, line_index=0, span_index=0, y0=50, y1=62),
            _frag("remove your proxy.", block_index=0, line_index=1, span_index=0, y0=65, y1=77),
        )
        blocks = group_source_fragments_into_blocks(frags)
        assert len(blocks) == 1
        assert "You may now return," in blocks[0].text
        assert "remove your proxy." in blocks[0].text

    def test_two_blocks_caption_and_list_item(self):
        """The fixture from the real bug: caption + list item → 2 blocks."""
        frags = (
            _frag(
                "Figure 2.21 \u2013 IP while on proxy",
                block_index=0,
                line_index=0,
                span_index=0,
                y0=50,
                y1=62,
            ),
            _frag(
                "7. You may now return, remove your proxy, and close the web browser.",
                block_index=1,
                line_index=0,
                span_index=0,
                y0=80,
                y1=92,
            ),
        )
        blocks = group_source_fragments_into_blocks(frags)
        assert len(blocks) == 2
        assert blocks[0].block_index == 0
        assert "Figure 2.21" in blocks[0].text
        assert blocks[1].block_index == 1
        assert "7." in blocks[1].text
        assert "return" in blocks[1].text

    def test_block_bbox_is_union_of_lines(self):
        """Block bbox covers all its lines."""
        frags = (
            _frag("Line A", block_index=0, line_index=0, span_index=0, x0=10, y0=50, x1=200, y1=62),
            _frag("Line B", block_index=0, line_index=1, span_index=0, x0=15, y0=65, x1=190, y1=77),
        )
        blocks = group_source_fragments_into_blocks(frags)
        bbox = blocks[0].bbox
        assert bbox.x0 == 10.0
        assert bbox.x1 == 200.0
        assert bbox.y0 == 50.0
        assert bbox.y1 == 77.0
