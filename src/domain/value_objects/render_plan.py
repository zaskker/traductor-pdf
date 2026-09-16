from dataclasses import dataclass, field
from enum import Enum, auto

from src.domain.models.enums import FitStatus, TextAlignment, TextWrapMode
from src.domain.value_objects.geometry import Rect


class BlockStructure(Enum):
    PARAGRAPH = auto()
    LIST = auto()
    LINE_ORIENTED = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class TextBlockPlan:
    rect: Rect
    text: str
    font_size: float
    font_family: str
    font_color: tuple[int, int, int] = (0, 0, 0)
    alignment: TextAlignment = TextAlignment.LEFT
    wrap_mode: TextWrapMode = TextWrapMode.WRAP
    structure: BlockStructure = BlockStructure.UNKNOWN

    def __post_init__(self):
        import math
        if self.rect.width <= 0 or self.rect.height <= 0:
            raise ValueError("TextBlockPlan: degenerate rect")
        if not self.text or not self.text.strip():
            raise ValueError("TextBlockPlan: text empty")
        if math.isnan(self.font_size) or math.isinf(self.font_size) or self.font_size <= 0:
            raise ValueError("TextBlockPlan: font_size must be positive finite")


@dataclass(frozen=True)
class RegionRenderPlan:
    region_id: str
    page_number: int
    target_rect: Rect
    blocks: tuple[TextBlockPlan, ...]
    background_rgb: tuple[int, int, int]
    fit_status: FitStatus

    def __post_init__(self):
        if not self.region_id or not self.region_id.strip():
            raise ValueError("region_id empty")
        if self.page_number < 1:
            raise ValueError("page_number < 1")
        if self.target_rect.width <= 0 or self.target_rect.height <= 0:
            raise ValueError("degenerate target_rect")
        if len(self.background_rgb) != 3:
            raise ValueError("background_rgb must have exactly 3 components")
