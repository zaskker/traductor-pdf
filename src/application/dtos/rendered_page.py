from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedPage:
    """
    Representa una página de PDF renderizada como píxeles, de manera completamente
    neutral a la tecnología gráfica (sin acoplamiento a Qt ni a PyMuPDF).
    """

    page_number: int  # 1-based index
    width: int
    height: int
    stride: int
    samples: bytes
    format: str  # e.g., 'RGB888' o 'RGBA8888'
    render_scale: float  # El factor utilizado para generar esta imagen (1.0 = base)

    # Dimensiones lógicas sin escalar, útiles para cálculos de bounding boxes después
    logical_width: float
    logical_height: float
