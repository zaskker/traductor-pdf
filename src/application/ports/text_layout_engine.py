from typing import Protocol

from src.domain.value_objects.layout import TextLayoutInput, TextLayoutResult


class ITextLayoutEngine(Protocol):
    def layout_text(self, input_data: TextLayoutInput) -> TextLayoutResult:
        """
        Calcula el layout del texto para un rectángulo y devuelve la información de fitting y las líneas generadas.
        """
