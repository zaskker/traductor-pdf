from src.application.dtos.pdf_selection import PdfSelection
from src.application.ports.text_extractor import ITextExtractor
from src.domain.value_objects.extraction import TextExtractionResult


class TextExtractionService:
    def __init__(self, extractor: ITextExtractor):
        self._extractor = extractor

    def extract_from_selection(self, selection: PdfSelection) -> TextExtractionResult:
        if not selection or not selection.pdf_rect:
            raise ValueError("Invalid selection")

        # The extraction happens purely using the native PDF rect.
        # No transforms are applied here.
        return self._extractor.extract(
            page_number=selection.page_number, selection=selection.pdf_rect
        )
