from dataclasses import dataclass
from enum import Enum

from src.domain.models.enums import ExtractionMethod
from src.domain.value_objects.geometry import Rect


class FragmentGranularity(str, Enum):
    SPAN = "span"
    WORD = "word"


@dataclass(frozen=True)
class SourceFragment:
    text: str
    bbox: Rect
    granularity: FragmentGranularity
    block_index: int
    line_index: int
    span_index: int
    raw_font_name: str
    font_size: float
    font_color: str  # Format: "#RRGGBB"
    font_flags_raw: int
    is_bold: bool
    is_italic: bool
    is_serif: bool
    is_monospace: bool


@dataclass(frozen=True)
class TextExtractionResult:
    page_number: int
    selection_rect: Rect
    source_bbox: Rect | None
    text: str
    fragments: tuple[SourceFragment, ...]
    extraction_method: ExtractionMethod
    warnings: tuple[str, ...]
