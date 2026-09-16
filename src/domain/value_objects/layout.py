from dataclasses import dataclass

from src.domain.models.enums import FitStatus, TextWrapMode, TextAlignment
from src.domain.value_objects.geometry import Rect


from src.domain.value_objects.render_plan import BlockStructure

@dataclass(frozen=True)
class TextLayoutInput:
    text: str
    target_rect: Rect
    min_font_size: float
    max_font_size: float
    font_family: str
    is_single_line_source: bool = False
    alignment: TextAlignment = TextAlignment.LEFT
    structure: BlockStructure = BlockStructure.UNKNOWN


@dataclass(frozen=True)
class TextLayoutLine:
    """
    Representa una línea extraída con su desplazamiento vertical respecto al rectángulo contenedor.
    """

    text: str
    y_offset: float


@dataclass(frozen=True)
class TextLayoutResult:
    font_size: float
    status: FitStatus
    lines: tuple[TextLayoutLine, ...]
    wrap_mode: TextWrapMode = TextWrapMode.WRAP


@dataclass(frozen=True)
class RenderedTextPreview:
    samples: bytes
    width: int
    height: int
    stride: int
    channels: int
    render_scale: float
