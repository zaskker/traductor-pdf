from dataclasses import dataclass

from src.domain.value_objects.geometry import Rect


@dataclass(frozen=True)
class PdfSelection:
    page_number: int  # 1-based index
    pdf_rect: Rect
    rendered_rect: Rect | None = None  # Coordenadas en píxeles renderizados de la imagen original
