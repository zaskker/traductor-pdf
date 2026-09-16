from src.domain.models.region import TranslationRegion
from src.domain.value_objects.layout import TextLayoutInput


class TextLayoutRequestFactory:
    """
    Construye las solicitudes de layout compartiendo exactamente
    la misma política para Preview (ViewModel) y Export (Preflight).
    """

    DEFAULT_MIN_FONT_SIZE = 6.0
    DEFAULT_MAX_FONT_SIZE = 24.0
    DEFAULT_FONT_FAMILY = "notos"  # Noto Sans via pymupdf-fonts (Unicode-safe, SIL OFL)

    @classmethod
    def create_input(cls, region: TranslationRegion) -> TextLayoutInput | None:
        if not region.translated_text:
            return None

        target_rect = region.selection_rect

        # Font policy
        max_font_size = region.get_dominant_font_size(
            default_max_font_size=cls.DEFAULT_MAX_FONT_SIZE,
            default_min_font_size=cls.DEFAULT_MIN_FONT_SIZE,
        )

        return TextLayoutInput(
            text=region.translated_text,
            target_rect=target_rect,
            min_font_size=cls.DEFAULT_MIN_FONT_SIZE,
            max_font_size=max_font_size,
            font_family=cls.DEFAULT_FONT_FAMILY,
        )
