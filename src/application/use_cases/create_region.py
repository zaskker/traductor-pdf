import uuid
from datetime import UTC, datetime

from src.application.dtos.pdf_selection import PdfSelection
from src.domain.models.enums import ExtractionMethod, RegionStatus, RegionType
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import TextExtractionResult


class CreateTranslationRegionUseCase:
    def execute(
        self,
        project: Project,
        selection: PdfSelection,
        extraction_result: TextExtractionResult,
    ) -> TranslationRegion:

        now = datetime.now(UTC)

        region = TranslationRegion(
            id=str(uuid.uuid4()),
            project_id=project.id,
            page_id=selection.page_number,  # 1-based UI numbering
            selection_rect=selection.pdf_rect,
            source_bbox=extraction_result.source_bbox,
            source_text=extraction_result.text,
            source_fragments=list(extraction_result.fragments)
            if extraction_result.fragments
            else [],
            translated_text="",
            region_type=RegionType.TEXT_NATIVE,
            status=RegionStatus.PENDING,
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            created_at=now,
            updated_at=now,
        )
        return region
