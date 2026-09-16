from src.application.ports.text_extractor import ITextExtractor
from src.domain.models.enums import ExtractionMethod
from src.domain.value_objects.extraction import (
    FragmentGranularity,
    SourceFragment,
    TextExtractionResult,
)
from src.domain.value_objects.geometry import Rect


class PyMuPDFTextExtractor(ITextExtractor):
    _CANDIDATE_MARGIN = 50.0
    _SPAN_OVERLAP_THRESHOLD = 0.50
    _WORD_FALLBACK_THRESHOLD = 0.70
    _SPACE_GAP_FACTOR = 0.15

    def __init__(self, document_adapter):
        self._adapter = document_adapter

    def extract(self, page_number: int, selection: Rect) -> TextExtractionResult:
        # page_number is 1-based
        if page_number < 1:
            raise ValueError(f"Invalid page_number (must be >= 1): {page_number}")

        page_index = page_number - 1

        # 1. Candidate Clip: Expand to prevent PyMuPDF from truncating spans
        # 50.0pt is the empirically tested value that guarantees spans are returned
        # intact for accurate geometric filtering, without causing performance issues.
        clip_coords = (
            selection.x0 - self._CANDIDATE_MARGIN,
            selection.y0 - self._CANDIDATE_MARGIN,
            selection.x1 + self._CANDIDATE_MARGIN,
            selection.y1 + self._CANDIDATE_MARGIN,
        )

        # Flags: Preserve whitespace, ligatures, NO images
        flags = 2 | 4  # 2 = TEXT_PRESERVE_LIGATURES, 4 = TEXT_PRESERVE_WHITESPACE

        text_dict = self._adapter.extract_text_dict_native(page_index, clip_coords, flags)

        accepted_spans = []
        for block_idx, block in enumerate(text_dict.get("blocks", [])):
            if block.get("type") != 0:  # Ignore image blocks just in case
                continue

            for line_idx, line in enumerate(block.get("lines", [])):
                for span_idx, span in enumerate(line.get("spans", [])):
                    span_rect = Rect(
                        span["bbox"][0], span["bbox"][1], span["bbox"][2], span["bbox"][3]
                    )
                    intersect = span_rect.intersect(selection)

                    if intersect.area > 0:
                        has_center = selection.contains_point(span_rect.center)
                        overlap_ratio = intersect.area / span_rect.area if span_rect.area > 0 else 0

                        # Span inclusion rule
                        if has_center or overlap_ratio >= self._SPAN_OVERLAP_THRESHOLD:
                            accepted_spans.append(
                                (block_idx, line_idx, span_idx, span, span_rect, overlap_ratio)
                            )

        # Word Fallback Trigger evaluation
        trigger_fallback = False

        if len(accepted_spans) == 0:
            trigger_fallback = True
        else:
            # If the user selected less than 70% of the total span area they touched,
            # they probably aimed for specific words (threshold 0.70 chosen by evidence)
            avg_overlap = sum(s[5] for s in accepted_spans) / len(accepted_spans)
            if avg_overlap < self._WORD_FALLBACK_THRESHOLD:
                trigger_fallback = True

        fragments = []
        if trigger_fallback:
            # Word Fallback
            words = self._adapter.extract_words_native(page_index, clip_coords)
            for w in words:
                w_rect = Rect(w[0], w[1], w[2], w[3])
                intersect = w_rect.intersect(selection)
                if intersect.area > 0:
                    has_center = selection.contains_point(w_rect.center)
                    overlap_ratio = intersect.area / w_rect.area if w_rect.area > 0 else 0

                    if has_center or overlap_ratio >= self._SPAN_OVERLAP_THRESHOLD:
                        # Find parent span to steal typographics
                        parent_span = self._find_parent_span(w_rect, text_dict)
                        fragments.append(
                            self._create_fragment(
                                text=w[4],
                                bbox=w_rect,
                                granularity=FragmentGranularity.WORD,
                                parent_span=parent_span,
                                fallback_block=w[5],
                                fallback_line=w[6],
                            )
                        )
        else:
            for b_idx, l_idx, s_idx, span, span_rect, _ in accepted_spans:
                fragments.append(
                    self._create_fragment(
                        text=span["text"],
                        bbox=span_rect,
                        granularity=FragmentGranularity.SPAN,
                        parent_span=(b_idx, l_idx, s_idx, span),
                    )
                )

        if not fragments:
            return TextExtractionResult(
                page_number=page_number,
                selection_rect=selection,
                source_bbox=None,
                text="",
                fragments=(),
                extraction_method=ExtractionMethod.NONE,
                warnings=("NO_NATIVE_TEXT",),
            )

        # Reconstruct source text
        source_text = self._reconstruct_text(fragments)

        # Source bbox is the union of all fragment bboxes
        s_x0 = min(f.bbox.x0 for f in fragments)
        s_y0 = min(f.bbox.y0 for f in fragments)
        s_x1 = max(f.bbox.x1 for f in fragments)
        s_y1 = max(f.bbox.y1 for f in fragments)
        source_bbox = Rect(s_x0, s_y0, s_x1, s_y1)

        return TextExtractionResult(
            page_number=page_number,
            selection_rect=selection,
            source_bbox=source_bbox,
            text=source_text,
            fragments=tuple(fragments),
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            warnings=(),
        )

    def _find_parent_span(
        self, word_rect: Rect, text_dict: dict
    ) -> tuple[int, int, int, dict] | None:
        """Heuristic to find the parent span of a word by maximum intersection."""
        best_span = None
        max_overlap = 0.0

        for b_idx, block in enumerate(text_dict.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for l_idx, line in enumerate(block.get("lines", [])):
                for s_idx, span in enumerate(line.get("spans", [])):
                    span_rect = Rect(*span["bbox"])
                    intersect = span_rect.intersect(word_rect)
                    if intersect.area > max_overlap:
                        max_overlap = intersect.area
                        best_span = (b_idx, l_idx, s_idx, span)
        return best_span

    def _create_fragment(
        self,
        text: str,
        bbox: Rect,
        granularity: FragmentGranularity,
        parent_span: tuple[int, int, int, dict] | None = None,
        fallback_block: int = 0,
        fallback_line: int = 0,
    ) -> SourceFragment:
        if parent_span:
            b_idx, l_idx, s_idx, span = parent_span
            font_flags = span.get("flags", 0)
            color_int = span.get("color", 0)
            color_hex = f"#{color_int:06x}" if color_int is not None else "#000000"

            return SourceFragment(
                text=text,
                bbox=bbox,
                granularity=granularity,
                block_index=b_idx,
                line_index=l_idx,
                span_index=s_idx,
                raw_font_name=span.get("font", "Unknown"),
                font_size=span.get("size", 12.0),
                font_color=color_hex,
                font_flags_raw=font_flags,
                is_bold=bool(font_flags & 16),
                is_italic=bool(font_flags & 2),
                is_serif=bool(font_flags & 4),
                is_monospace=bool(font_flags & 8),
            )
        else:
            return SourceFragment(
                text=text,
                bbox=bbox,
                granularity=granularity,
                block_index=fallback_block,
                line_index=fallback_line,
                span_index=0,
                raw_font_name="Unknown",
                font_size=12.0,
                font_color="#000000",
                font_flags_raw=0,
                is_bold=False,
                is_italic=False,
                is_serif=False,
                is_monospace=False,
            )

    def _reconstruct_text(self, fragments: list[SourceFragment]) -> str:
        """
        Reconstructs text by structurally grouping blocks, lines, and spans.
        No aggressive spatial heuristics, we rely purely on block/line/span structure
        which handles reading order nicely and deterministically.
        """
        # Sort structurally
        sorted_frags = sorted(
            fragments, key=lambda f: (f.block_index, f.line_index, f.span_index, f.bbox.x0)
        )

        blocks = {}
        for f in sorted_frags:
            if f.block_index not in blocks:
                blocks[f.block_index] = {}
            if f.line_index not in blocks[f.block_index]:
                blocks[f.block_index][f.line_index] = []
            blocks[f.block_index][f.line_index].append(f)

        block_texts = []
        for b_idx in sorted(blocks.keys()):
            line_texts = []
            for l_idx in sorted(blocks[b_idx].keys()):
                # Within a line, fragments are already sorted by span_index and x0
                frags = blocks[b_idx][l_idx]

                # If granularity is WORD, we need to add spaces between words manually,
                # because `get_text("words")` strips them.
                # If granularity is SPAN, PyMuPDF usually includes trailing spaces in the span text itself.
                line_str = ""
                for i, f in enumerate(frags):
                    line_str += f.text

                    if i < len(frags) - 1:
                        next_f = frags[i + 1]
                        # Don't add space if we already have one, or if the next fragment starts with one
                        if not line_str.endswith(" ") and not next_f.text.startswith(" "):
                            # If no trailing/leading space exists, check geometric gap to the next fragment.
                            # A standard space width is usually ~0.25 * font_size.
                            # We use > 0.15 * font_size as a threshold for a space.
                            gap = next_f.bbox.x0 - f.bbox.x1
                            if gap > self._SPACE_GAP_FACTOR * f.font_size:
                                line_str += " "

                line_texts.append(line_str)
            block_texts.append("\n".join(line_texts))

        return "\n\n".join(block_texts)
