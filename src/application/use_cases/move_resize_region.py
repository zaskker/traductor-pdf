from datetime import UTC, datetime

from src.application.dtos.pdf_selection import PdfSelection
from src.application.services.text_extraction import TextExtractionService
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import ExtractionMethod
from src.domain.value_objects.geometry import Rect


class MoveResizeRegionError(Exception):
    pass


class MoveResizeRegionUseCase:
    def __init__(self, extraction_service: TextExtractionService):
        self.extraction_service = extraction_service

    def execute(
        self,
        project: Project,
        old_region: TranslationRegion,
        new_pdf_rect: Rect,
        is_project_locked: bool = False,
    ) -> TranslationRegion:
        if is_project_locked:
            raise MoveResizeRegionError("Cannot edit regions in a locked project")

        selection = PdfSelection(page_number=old_region.page_id, pdf_rect=new_pdf_rect)

        result = self.extraction_service.extract_from_selection(selection)

        if result.extraction_method == ExtractionMethod.NONE or not result.fragments:
            raise MoveResizeRegionError("No text found in the new region")

        now = datetime.now(UTC)

        from src.domain.models.enums import RegionStatus

        if result.text == old_region.source_text:
            translated_text = old_region.translated_text
            status = old_region.status
            is_manually_edited = old_region.is_manually_edited
        else:
            translated_text = ""
            status = RegionStatus.PENDING
            is_manually_edited = False

        new_region = TranslationRegion(
            id=old_region.id,
            project_id=old_region.project_id,
            page_id=old_region.page_id,
            selection_rect=new_pdf_rect,
            source_bbox=result.source_bbox,
            source_text=result.text,
            source_fragments=result.fragments,
            extraction_method=result.extraction_method,
            translated_text=translated_text,
            status=status,
            is_manually_edited=is_manually_edited,
            region_type=old_region.region_type,
            created_at=old_region.created_at,
            updated_at=now,
        )

        return new_region
