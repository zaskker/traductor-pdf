from dataclasses import dataclass
from datetime import datetime

from src.domain.models.enums import ExtractionMethod, FitStatus, RegionStatus, RegionType, ReviewStatus
from src.domain.value_objects.extraction import SourceFragment
from src.domain.value_objects.geometry import Rect


@dataclass
class TranslationRegion:
    """Región de traducción que encapsula intención geométrica y contenido extraído."""

    id: str
    project_id: str
    page_id: int
    selection_rect: Rect

    source_bbox: Rect | None = None
    source_fragments: list[SourceFragment] | None = None

    source_text: str = ""
    translated_text: str = ""
    is_manually_edited: bool = False

    region_type: RegionType = RegionType.TEXT_NATIVE
    status: RegionStatus = RegionStatus.PENDING
    extraction_method: ExtractionMethod = ExtractionMethod.NATIVE_TEXT

    source_font_family: str | None = None
    source_font_size: float | None = None
    source_font_color: str | None = None
    source_alignment: str | None = None
    source_line_height: float | None = None

    target_font_family: str | None = None
    target_font_size: float | None = None
    target_alignment: str | None = None
    target_line_height: float | None = None

    translation_engine: str | None = None
    translation_engine_version: str | None = None
    translation_model: str | None = None


    fit_status: FitStatus = FitStatus.PENDING
    fit_scale: float | None = None

    translated_blocks: list[dict] | None = None
    prompt_template_version: str | None = None
    translation_options: dict | None = None
    glossary_id: str | None = None
    glossary_revision: int | None = None
    translation_revision: int | None = None

    # TRANS-05: Review / Approval workflow
    # State is DERIVED from these fields + translation_revision. No mutable review_status field.
    reviewed_translation_revision: int | None = None
    approved_translation_revision: int | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def review_status(self) -> ReviewStatus:
        """Derive effective review status from persisted revision metadata.

        Rules (in priority order):
        - UNTRANSLATED: no valid translation_revision exists
        - APPROVED: approved_translation_revision == translation_revision
        - REVIEWED: reviewed_translation_revision == translation_revision
        - UNREVIEWED: otherwise
        """
        if self.translation_revision is None:
            return ReviewStatus.UNTRANSLATED
        if self.approved_translation_revision == self.translation_revision:
            return ReviewStatus.APPROVED
        if self.reviewed_translation_revision == self.translation_revision:
            return ReviewStatus.REVIEWED
        return ReviewStatus.UNREVIEWED

    def change_status(self, new_status: RegionStatus):
        valid_transitions = {
            RegionStatus.PENDING: [
                RegionStatus.TRANSLATED,
                RegionStatus.ERROR,
                RegionStatus.IGNORED,
            ],
            RegionStatus.TRANSLATED: [
                RegionStatus.REVIEWED,
                RegionStatus.PENDING,
                RegionStatus.ERROR,
            ],
            RegionStatus.REVIEWED: [
                RegionStatus.READY_FOR_EXPORT,
                RegionStatus.TRANSLATED,
                RegionStatus.PENDING,
            ],
            RegionStatus.READY_FOR_EXPORT: [
                RegionStatus.EXPORTED,
                RegionStatus.REVIEWED,
                RegionStatus.PENDING,
            ],
            RegionStatus.EXPORTED: [RegionStatus.REVIEWED, RegionStatus.PENDING],
            RegionStatus.ERROR: [RegionStatus.PENDING, RegionStatus.TRANSLATED],
            RegionStatus.IGNORED: [RegionStatus.PENDING],
        }

        if new_status not in valid_transitions.get(self.status, []):
            raise ValueError(f"Transición de estado inválida: {self.status} -> {new_status}")

        self.status = new_status

    def get_dominant_font_size(
        self, default_max_font_size: float = 24.0, default_min_font_size: float = 6.0
    ) -> float:
        """
        Calcula el tamaño de fuente predominante (weighted by character count).
        Filtra valores inválidos, NaN, Inf, o absurdos.
        """
        import math

        if not self.source_fragments:
            return default_max_font_size

        size_counts: dict[float, int] = {}
        for fragment in self.source_fragments:
            size = fragment.font_size
            if size is None or math.isnan(size) or math.isinf(size) or size <= 0 or size > 1000:
                continue

            # Agrupar tamaños parecidos (e.g. 11.999 y 12.0)
            rounded_size = round(size, 1)
            char_count = len(fragment.text)
            size_counts[rounded_size] = size_counts.get(rounded_size, 0) + char_count

        if not size_counts:
            return default_max_font_size

        dominant_size = max(size_counts.items(), key=lambda x: x[1])[0]

        if dominant_size < default_min_font_size:
            return default_min_font_size

        return float(dominant_size)

    def get_dominant_font_color(self, default_color: str = "#000000") -> str:
        if not self.source_fragments:
            return default_color
            
        color_counts: dict[str, int] = {}
        for fragment in self.source_fragments:
            color = fragment.font_color
            if not color or not color.startswith("#"):
                continue
            char_count = len(fragment.text)
            color_counts[color] = color_counts.get(color, 0) + char_count
            
        if not color_counts:
            return default_color
            
        return max(color_counts.items(), key=lambda x: x[1])[0]
