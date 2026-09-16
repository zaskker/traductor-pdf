"""
block_grouper.py — Application-layer helper for grouping SourceFragments into logical lines.

Uses real SourceFragment domain objects. No mocks, no SimpleNamespace.
Pure Python — no PyMuPDF dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.extraction import SourceFragment
from src.domain.value_objects.geometry import Rect


@dataclass(frozen=True)
class SourceTextLine:
    """
    A single visual line within a PDF, derived from one or more SourceFragments
    sharing the same (block_index, line_index).
    """

    block_index: int
    line_index: int
    bbox: Rect  # union of all fragment bboxes on this line
    text: str  # concatenated span text in span_index / x0 order
    font_size: float  # dominant font size on this line


@dataclass(frozen=True)
class SourceTextBlock:
    """
    A logical block (paragraph, list item, caption, etc.) composed of one or
    more SourceTextLines sharing the same block_index.
    """

    block_index: int
    lines: tuple[SourceTextLine, ...]
    bbox: Rect  # union of all line bboxes
    text: str  # full block text (lines joined with space, preserving inline wrap)

    @property
    def first_line(self) -> SourceTextLine:
        return self.lines[0]


def _union_rect(rects: list[Rect]) -> Rect:
    x0 = min(r.x0 for r in rects)
    y0 = min(r.y0 for r in rects)
    x1 = max(r.x1 for r in rects)
    y1 = max(r.y1 for r in rects)
    return Rect(x0, y0, x1, y1)


def group_source_fragments_into_lines(
    fragments: tuple[SourceFragment, ...],
) -> tuple[SourceTextLine, ...]:
    """
    Group SourceFragments by (block_index, line_index), sorted within each
    line by span_index then bbox.x0.

    Args:
        fragments: tuple of real SourceFragment domain objects.

    Returns:
        Tuple of SourceTextLine in reading order (block_index ASC, line_index ASC).
    """
    if not fragments:
        return ()

    # Group by (block_index, line_index)
    groups: dict[tuple[int, int], list[SourceFragment]] = {}
    for frag in fragments:
        key = (frag.block_index, frag.line_index)
        groups.setdefault(key, []).append(frag)

    result: list[SourceTextLine] = []
    for (block_idx, line_idx), frags in sorted(groups.items()):
        # Sort within line: span_index primary, bbox.x0 secondary
        sorted_frags = sorted(
            frags,
            key=lambda f: (f.span_index, f.bbox.x0 if f.bbox else 0),
        )

        # Filter out fragments without valid bbox
        valid_frags = [f for f in sorted_frags if f.bbox]
        if not valid_frags:
            continue

        # Build text: concatenate span texts with no separator (spans are adjacent)
        line_text = "".join(f.text for f in sorted_frags if f.text)

        # Union bbox
        bbox = _union_rect([f.bbox for f in valid_frags])

        # Dominant font size: largest font_size among fragments
        font_size = max((f.font_size for f in sorted_frags if f.font_size), default=12.0)

        result.append(
            SourceTextLine(
                block_index=block_idx,
                line_index=line_idx,
                bbox=bbox,
                text=line_text,
                font_size=font_size,
            )
        )

    return tuple(result)


def group_lines_into_blocks(
    lines: tuple[SourceTextLine, ...],
) -> tuple[SourceTextBlock, ...]:
    """
    Group SourceTextLines by block_index into logical blocks.

    Args:
        lines: output of group_source_fragments_into_lines().

    Returns:
        Tuple of SourceTextBlock in block_index order.
    """
    if not lines:
        return ()

    blocks: dict[int, list[SourceTextLine]] = {}
    for line in lines:
        blocks.setdefault(line.block_index, []).append(line)

    result: list[SourceTextBlock] = []
    for block_idx in sorted(blocks.keys()):
        block_lines = blocks[block_idx]
        bbox = _union_rect([ln.bbox for ln in block_lines])

        # Join lines into block text — use space because PDF lines are visual wrap
        # of the same logical sentence; the LLM will produce a translated unit.
        block_text = " ".join(ln.text.strip() for ln in block_lines if ln.text.strip())

        result.append(
            SourceTextBlock(
                block_index=block_idx,
                lines=tuple(block_lines),
                bbox=bbox,
                text=block_text,
            )
        )

    return tuple(result)


def group_source_fragments_into_blocks(
    fragments: tuple[SourceFragment, ...],
) -> tuple[SourceTextBlock, ...]:
    """
    Convenience: go directly from SourceFragment → SourceTextBlock.

    This is the primary API for callers that need block-level structure
    without caring about intermediate lines.
    """
    lines = group_source_fragments_into_lines(fragments)
    return group_lines_into_blocks(lines)
