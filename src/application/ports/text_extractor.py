from typing import Protocol

from src.domain.value_objects.extraction import TextExtractionResult
from src.domain.value_objects.geometry import Rect


class ITextExtractor(Protocol):
    def extract(self, page_number: int, selection: Rect) -> TextExtractionResult:
        """
        Extrae el texto nativo de una región del PDF.
        :param page_number: Índice de la página (0-indexed).
        :param selection: Región de selección en coordenadas nativas del PDF.
        :return: Resultado de la extracción con fragmentos e información de texto.
        """
        ...
