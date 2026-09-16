# ADR 006: Native Text Extraction and Source Fragments

## Context
During Phase 3, we needed to implement native text extraction from a `PdfSelection`. 
The core challenge was translating a geometric rectangle (provided by Phase 2) into structural text fragments (blocks, lines, spans, words) using PyMuPDF, while satisfying rigorous layout and reading-order constraints.

## Constraints and Requirements
1. **Geometric Fidelity**: Text must be included if and only if it meaningfully intersects the user's selection. Contiguous neighboring columns or lines must not be included.
2. **Structural Fidelity**: The extracted text must preserve reading order, spaces, and styling (bold/italic) to facilitate future translation and text replacement.
3. **Truncation Avoidance**: We must recover full spans rather than partial cut-off words when the user selects a region, so the translator has full context.
4. **Architectural Purity**: The Domain/Application layer must not depend on PyMuPDF types. Infrastructure implementation must not violate adapter encapsulation.

## Decision 1: Candidate Extraction with Large Margin
Instead of extracting text exactly within the user's rectangle (which causes PyMuPDF to truncate spans and destroy their original bounding boxes), we extract a *candidate pool* using a generously expanded `clip` margin (50.0pt).
- **Evidence**: Experiments showed that small margins (e.g., 2.0pt) caused PyMuPDF to return truncated spans like `['MarginTestWo']` instead of `['MarginTestWord']`. Truncated spans have smaller bounding boxes, which break overlap ratio calculations.
- **Result**: Margin = 50.0pt ensures spans are returned fully intact.

## Decision 2: Geometric Span Inclusion Rule
Once the candidate pool is extracted, we filter spans manually using a geometric intersection rule.
- **Rule**: A span is accepted if the user's selection covers at least 50% of the span's area (`overlap_ratio >= 0.5`).
- **Evidence**: Experiments showed this rule reliably rejects neighbor lines (overlap ~0.20) and completely avoids column contamination.

## Decision 3: Structural Reassembly for Reading Order
We deliberately reject PyMuPDF's `sort=True` flag for reading order.
- **Evidence**: `sort=True` attempts aggressive spatial heuristic sorting, which severely disrupts column-based layouts (it reads across columns instead of down). 
- **Rule**: We sort fragments structurally by `(block_index, line_index, span_index, x0)`. This effectively preserves PyMuPDF's robust block detection, solving column layouts implicitly.

## Decision 4: Geometric Space Reconstruction
PyMuPDF's `get_text("words")` strips spaces, and `get_text("dict")` does not always guarantee spaces between spans.
- **Rule**: During text reconstruction, we calculate the horizontal gap to the next fragment. If `gap > 0.15 * font_size`, we manually inject a space.
- **Evidence**: This prevents bugs like "Threatintelligence" while avoiding double spaces like "Threat  intelligence".

## Decision 5: Word Fallback Strategy
If the user selects a tiny portion of a text block (e.g., trying to translate a single word), the 50% span overlap rule might reject the entire span (since the single word is < 50% of the full sentence span).
- **Rule**: If the average overlap of accepted spans is `< 0.70`, we fallback to word-level granularity.
- **Evidence**: Tests showed that selecting a single word yields ~0.58 overlap, while a "slightly clipped" full sentence yields ~0.75. The 0.70 threshold effectively separates intentional word selection from sloppy line selection.

## Decision 6: Infrastructure Encapsulation
The `PyMuPDFTextExtractor` delegates actual PyMuPDF calls to `PyMuPDFDocument` via internal methods (`_extract_text_dict`, `_extract_words`).
- **Result**: This prevents the extractor from accessing `_adapter._doc` directly, maintaining strict boundary compliance within the infrastructure layer.

## Consequences
- **Positive**: We achieve robust text extraction that handles columns, margins, half-words, and stylistic metadata without resorting to OCR.
- **Negative**: The geometric calculations add a very slight computational overhead, but it is negligible for interactive, single-selection usage.


## Evidence Table

| Decision         | Options tested | Selected | Evidence |
| ---------------- | -------------- | -------- | -------- |
| Candidate margin | 0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0 pt | 50.0 pt | Small margins truncate spans (e.g. 'TargetLi' instead of 'TargetLine'). 50.0pt avoids truncation and allows precise geometric overlap calculation. |
| Span inclusion   | 48%, 49%, 50%, 51% | center OR >= 50% | Tests confirm that selections with exactly 50% overlap or containing the center are included, effectively filtering neighboring lines in observed fixtures. |
| Word fallback    | 0.60, 0.70, 0.80, 0.85, 0.90 | 0.70 | Single words yield ~0.58 overlap. Slightly clipped full lines yield ~0.75. 0.70 effectively triggers fallback only for intentional partial selections. |
| Reading order    | sort=False, sort=True, structural | structural | sort=True merges columns improperly. Structural assembler respects PyMuPDF's robust block parsing, retaining column fidelity. |
| Space gap        | 0.10, 0.14, 0.15, 0.16, 0.20 | > 0.15 * size | A gap of 0.15 times the font size reliably indicates intentional spacing, handling cases like Threat intelligence vs Threatintelligence. |
