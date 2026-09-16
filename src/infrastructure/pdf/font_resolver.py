"""
Font resolution for Unicode-safe PDF rendering.

Uses pymupdf-fonts (Noto Sans, SIL Open Font License) as the primary
Unicode font. This avoids any dependency on system-installed fonts and
is fully redistributable.

pymupdf-fonts is installed as a Python package and its font buffers are
accessed via `pymupdf.css_for_pymupdf_font()`. No file paths required.
"""

from __future__ import annotations

import pymupdf

# The font-code in pymupdf-fonts for Noto Sans (Regular/Bold/Italic/BoldItalic)
# SIL Open Font License — freely redistributable.
FONT_CODE = "notos"
FONT_FAMILY_CSS_NAME = "notos"


def build_unicode_css_and_archive() -> tuple[str, pymupdf.Archive]:
    """
    Build the CSS @font-face declarations and Archive for Noto Sans.

    Returns:
        (css_str, archive) — ready to pass to insert_htmlbox or Story.

    Raises:
        RuntimeError: if pymupdf-fonts is not installed or font not found.
    """
    try:
        archive = pymupdf.Archive()
        css = pymupdf.css_for_pymupdf_font(FONT_CODE, archive=archive)
        return css, archive
    except Exception as e:
        raise RuntimeError(
            f"pymupdf-fonts ({FONT_CODE}) not available. "
            "Install: pip install pymupdf-fonts. "
            f"Original error: {e}"
        ) from e


def font_family_name() -> str:
    """The CSS font-family name to reference in style rules."""
    return FONT_FAMILY_CSS_NAME
