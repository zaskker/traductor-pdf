"""
list_prefix_detector.py — Detects and extracts list/ordered-list prefixes from text.

Pure Python — no external dependencies.
Used by the export pipeline to protect list markers during translation
and layout so they stay inline with the body text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches common list prefixes at the start of a string:
#   "1."  "7."  "1)"  "a)"  "A."  "(1)"  "-"  "•"  "*"  "–"
_LIST_PREFIX_RE = re.compile(
    r"^("
    r"\(\d+\)\s+"  # (1) style
    r"|\d+[.)]\s+"  # 1. or 1) style
    r"|[a-zA-Z][.)]\s+"  # a. or a) style
    r"|[-•*–]\s+"  # bullet styles
    r")"
)


@dataclass(frozen=True)
class ListPrefixResult:
    prefix: str  # the extracted prefix (e.g. "7. ", "• ", "- ")
    body: str  # text after the prefix


def detect_list_prefix(text: str) -> ListPrefixResult | None:
    """
    Detect if text begins with a list/ordered-list prefix.

    Returns:
        ListPrefixResult(prefix, body) if found, else None.

    Examples:
        "7. You may now return..." → ListPrefixResult(prefix="7. ", body="You may now...")
        "• Click OK"               → ListPrefixResult(prefix="• ", body="Click OK")
        "Figure 2.21 – Caption"    → None
    """
    stripped = text.lstrip()
    if not stripped:
        return None

    m = _LIST_PREFIX_RE.match(stripped)
    if m:
        prefix = m.group(0)
        body = stripped[len(prefix) :]
        return ListPrefixResult(prefix=prefix, body=body)
    return None


def format_list_block(prefix: str, translated_body: str) -> str:
    """
    Reconstruct a list item as a single logical line: "7. translated body".

    The prefix from the source is kept exactly (number/bullet preserved).
    The translated body is the LLM output (without the prefix, if the
    translation prompt was given the body only).
    """
    # Normalise: strip trailing space from prefix, ensure single space separator
    return prefix.rstrip() + " " + translated_body.lstrip()
